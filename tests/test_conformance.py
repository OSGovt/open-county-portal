"""Run the conformance suite against a live server on the test database.

Accessibility checks run when Playwright, a Chromium browser and axe-core
(conformance/node_modules) are available; otherwise those checks are skipped
and the rest still run.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from portal import cli, config_store
from portal.db import tx
from portal.settings import reset_settings_cache

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "conformance"))
import run as conformance  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_url(tmp_path_factory):
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    old = os.environ["PORTAL_SITE_URL"]
    os.environ["PORTAL_SITE_URL"] = url
    reset_settings_cache()
    with tx() as conn:
        od = config_store.get(conn, "open_data")
        saved = dict(od)
        od.update(contact_name="Open data desk", contact_email="opendata@example-county.gov",
                  license_url="https://creativecommons.org/publicdomain/zero/1.0/")
        config_store.put(conn, "open_data", od, actor="test")
    cli.main(["export-bulk"])
    from portal.app import create_app
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            if httpx.get(url + "/healthz").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield url
    server.should_exit = True
    thread.join(timeout=10)
    with tx() as conn:
        config_store.put(conn, "open_data", saved, actor="test")
    os.environ["PORTAL_SITE_URL"] = old
    reset_settings_cache()


def test_conformance_suite_passes(live_url, tmp_path, capsys):
    code = conformance.main(["--url", live_url, "--max-pages", "25", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out[-4000:]
    assert "0 failed" in out
