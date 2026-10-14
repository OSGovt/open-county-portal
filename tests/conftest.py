"""Test setup: a fresh PostgreSQL database for each test run.

Set PORTAL_TEST_DATABASE_URL to an empty database the tests may drop and
recreate tables in, e.g. postgresql+psycopg://postgres@/portal_test?host=/tmp
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import pyotp
import pytest

TEST_DB = os.environ.get("PORTAL_TEST_DATABASE_URL", "postgresql+psycopg://postgres@/portal_test?host=/tmp")
DATA = Path(tempfile.mkdtemp(prefix="portal-test-"))
os.environ.update({"PORTAL_ENV": "test", "PORTAL_DATABASE_URL": TEST_DB, "PORTAL_DATA_DIR": str(DATA),
                   "PORTAL_SITE_URL": "http://testserver", "PORTAL_SECRET_KEY": "test-secret-key",
                   "PORTAL_SECURE_COOKIES": "false"})

from fastapi.testclient import TestClient  # noqa: E402

from portal import cli  # noqa: E402
from portal.db import get_engine, metadata, reset_engine  # noqa: E402
from portal.settings import reset_settings_cache  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    reset_settings_cache()
    reset_engine()
    engine = get_engine()
    metadata.drop_all(engine)
    cli.main(["setup", "--name", "Test County", "--type", "county", "--state", "tx",
              "--admin-email", "admin@test.gov", "--admin-name", "Test Admin"])
    cli.main(["demo"])
    yield engine
    shutil.rmtree(DATA, ignore_errors=True)


@pytest.fixture()
def client():
    from portal.app import create_app
    with TestClient(create_app()) as c:
        yield c


def csrf(client: TestClient, path: str) -> str:
    html = client.get(path).text
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert m, f"no CSRF token on {path}"
    return m.group(1)


def staff_login(client: TestClient, email: str = "admin@test.gov") -> None:
    """Sign in as a staff user, completing first-time password and MFA setup as needed."""
    from sqlalchemy import select
    from portal import auth
    from portal.db import tx, users
    with tx() as conn:
        row = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        conn.execute(users.update().where(users.c.id == row["id"]).values(
            password_hash=auth.hash_password("correct horse battery staple"), must_change_password=False,
            failed_logins=0, locked_until=None))
        secret = row["totp_secret"]
        enrolled = row["mfa_enrolled"]
    token = csrf(client, "/staff/login")
    r = client.post("/staff/login", data={"_csrf": token, "email": email, "password": "correct horse battery staple",
                                          "next": "/staff"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    path = "/staff/mfa/setup" if not enrolled else "/staff/mfa"
    token = csrf(client, path)
    r = client.post(path, data={"_csrf": token, "code": pyotp.TOTP(secret).now()}, follow_redirects=False)
    assert r.status_code == 303, r.text
