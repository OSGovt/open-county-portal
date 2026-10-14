"""Staff accounts: passwords, two-step sign-in codes, roles and lockout.

Public visitors never need an account. Staff sign in with a password and a
six-digit code from an authenticator app (TOTP). Five wrong attempts lock the
account for 15 minutes.
"""
from __future__ import annotations

import datetime as dt
import secrets
import string

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.engine import Connection

from .db import audit, users, utcnow

_hasher = PasswordHasher()

ROLES = {
    "admin": "Administrator: everything, including users, theme, settings and fees",
    "content": "Content editor: pages, services, offices, meetings and postings",
    "records": "Records clerk: records, certified copy orders, redaction requests",
    "cashier": "Cashier: counter point of sale for assigned offices",
    "supervisor": "Supervisor: voids, refunds, drawer close-out review",
    "finance": "Finance: reports and ledger exports",
    "pia": "Public information officer: open records requests",
    "applications": "Applications reviewer: forms such as permits and jury responses",
}

MIN_PASSWORD = 12
LOCK_AFTER = 5
LOCK_MINUTES = 15


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters. A short sentence works well."
    if password.lower() == password and password.isalpha() and len(password) < 20:
        return "Add a number, a capital letter, or make it longer (20 or more letters)."
    return None


def temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    words = ["".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4)]
    return "-".join(words)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    code = (code or "").replace(" ", "").strip()
    return code.isdigit() and pyotp.TOTP(secret).verify(code, valid_window=1)


def create_user(conn: Connection, email: str, name: str, roles: list[str], offices: list[str] | None = None,
                password: str | None = None, actor: str | None = None) -> str:
    """Create a staff account and return its temporary password."""
    email = email.strip().lower()
    bad = [r for r in roles if r not in ROLES]
    if bad:
        raise ValueError(f"Unknown role(s): {', '.join(bad)}. Choose from: {', '.join(ROLES)}.")
    if conn.execute(select(users.c.id).where(users.c.email == email)).first():
        raise ValueError(f"An account for {email} already exists.")
    temp = password or temporary_password()
    conn.execute(users.insert().values(email=email, name=name, password_hash=hash_password(temp), roles=roles,
                                       offices=offices or [], must_change_password=password is None,
                                       totp_secret=new_totp_secret(), mfa_enrolled=False))
    audit(conn, actor, "user.create", "user", email, {"roles": roles, "offices": offices or []})
    return temp


def attempt_login(conn: Connection, email: str, password: str, ip: str) -> tuple[dict | None, str | None]:
    row = conn.execute(select(users).where(users.c.email == (email or "").strip().lower())).mappings().first()
    generic = "That email and password don't match an active account."
    if row is None or not row["active"]:
        return None, generic
    now = utcnow()
    if row["locked_until"] and row["locked_until"] > now:
        minutes = int((row["locked_until"] - now).total_seconds() // 60) + 1
        return None, f"This account is locked after too many attempts. Try again in {minutes} minutes, or ask an administrator."
    if not verify_password(row["password_hash"], password):
        fails = row["failed_logins"] + 1
        values = {"failed_logins": fails}
        if fails >= LOCK_AFTER:
            values = {"failed_logins": 0, "locked_until": now + dt.timedelta(minutes=LOCK_MINUTES)}
        conn.execute(users.update().where(users.c.id == row["id"]).values(**values))
        audit(conn, row["email"], "login.failed", "user", row["email"], ip=ip)
        return None, generic
    conn.execute(users.update().where(users.c.id == row["id"]).values(failed_logins=0, locked_until=None))
    return dict(row), None


STAFF_IDLE_SECONDS = 60 * 60


def current_staff(request: Request, conn: Connection) -> dict | None:
    import time
    uid = request.session.get("staff_id")
    if not uid or not request.session.get("staff_mfa_ok"):
        return None
    from .settings import get_settings
    now = time.time()
    seen = request.session.get("staff_seen", now)
    since = request.session.setdefault("staff_since", now)
    if now - seen > STAFF_IDLE_SECONDS or now - since > get_settings().staff_session_max_age:
        for key in ("staff_id", "staff_name", "staff_mfa_ok", "staff_seen", "staff_since"):
            request.session.pop(key, None)
        return None
    request.session["staff_seen"] = now
    row = conn.execute(select(users).where(users.c.id == uid, users.c.active.is_(True))).mappings().first()
    return dict(row) if row else None


def has_role(user: dict | None, *roles: str) -> bool:
    if not user:
        return False
    mine = set(user.get("roles") or [])
    return "admin" in mine or bool(mine.intersection(roles))


def require(request: Request, conn: Connection, *roles: str) -> dict:
    user = current_staff(request, conn)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": f"/staff/login?next={request.url.path}"})
    if user.get("must_change_password") and request.url.path not in ("/staff/password", "/staff/logout"):
        raise HTTPException(status_code=303, headers={"Location": "/staff/password"})
    if roles and not has_role(user, *roles):
        raise HTTPException(status_code=403, detail="Your account doesn't have permission for this page. Ask an administrator.")
    return user
