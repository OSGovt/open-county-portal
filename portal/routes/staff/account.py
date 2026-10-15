"""Sign in, two-step codes, first-time setup, password change, sign out."""
from __future__ import annotations

import io

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from markupsafe import Markup
from sqlalchemy import select

from ... import auth, config_store
from ...db import audit, get_engine, tx, users, utcnow
from ...web import client_ip, flash, render, verify_csrf

router = APIRouter()


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/staff") and not target.startswith("//"):
        return target
    return "/staff"


@router.get("/login")
def login_page(request: Request, next: str = "/staff"):
    with get_engine().connect() as conn:
        return render(request, "staff/login.html", conn, page_title="Staff sign in", next=_safe_next(next), error=None,
                      demo=auth.demo_mode() and auth.demo_code(conn) is not None,
                      demo_email=auth.DEMO_STAFF_EMAIL, demo_password=auth.DEMO_STAFF_PASSWORD)


@router.post("/login", dependencies=[Depends(verify_csrf)])
async def login_submit(request: Request):
    form = await request.form()
    nxt = _safe_next(str(form.get("next", "")))
    with tx() as conn:
        user, error = auth.attempt_login(conn, str(form.get("email", "")), str(form.get("password", "")), client_ip(request))
        if user is None:
            return render(request, "staff/login.html", conn, status_code=400, page_title="Staff sign in", next=nxt,
                          error=error, email=form.get("email", ""))
    request.session.clear()
    request.session["staff_pending"] = user["id"]
    request.session["staff_next"] = nxt
    if not user["mfa_enrolled"]:
        return RedirectResponse("/staff/mfa/setup", status_code=303)
    return RedirectResponse("/staff/mfa", status_code=303)


def _pending(conn, request) -> dict | None:
    uid = request.session.get("staff_pending")
    if not uid:
        return None
    row = conn.execute(select(users).where(users.c.id == uid, users.c.active.is_(True))).mappings().first()
    return dict(row) if row else None


@router.get("/mfa")
def mfa_page(request: Request):
    with get_engine().connect() as conn:
        pending = _pending(conn, request)
        if pending is None:
            return RedirectResponse("/staff/login", status_code=303)
        code = auth.demo_code(conn) if auth.is_demo_account(pending["email"]) else None
        return render(request, "staff/mfa.html", conn, page_title="Enter your code", error=None, demo_code=code)


def _finish_login(request: Request, conn, user: dict) -> RedirectResponse:
    nxt = request.session.get("staff_next", "/staff")
    request.session.pop("staff_pending", None)
    request.session["staff_id"] = user["id"]
    request.session["staff_name"] = user["name"]
    request.session["staff_mfa_ok"] = True
    import time as _time
    request.session["staff_since"] = _time.time()
    request.session["staff_seen"] = _time.time()
    conn.execute(users.update().where(users.c.id == user["id"]).values(last_login=utcnow()))
    audit(conn, user["email"], "login.success", "user", user["email"], ip=client_ip(request))
    if user["must_change_password"]:
        return RedirectResponse("/staff/password", status_code=303)
    return RedirectResponse(nxt, status_code=303)


@router.post("/mfa", dependencies=[Depends(verify_csrf)])
async def mfa_submit(request: Request):
    form = await request.form()
    with tx() as conn:
        user = _pending(conn, request)
        if user is None:
            return RedirectResponse("/staff/login", status_code=303)
        if not auth.verify_totp(user["totp_secret"], str(form.get("code", ""))):
            audit(conn, user["email"], "mfa.failed", "user", user["email"], ip=client_ip(request))
            code = auth.demo_code(conn) if auth.is_demo_account(user["email"]) else None
            return render(request, "staff/mfa.html", conn, status_code=400, page_title="Enter your code",
                          error="That code didn't match. Codes change every 30 seconds; enter the one showing now.",
                          demo_code=code)
        return _finish_login(request, conn, user)


def _qr_svg(uri: str) -> Markup:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    svg = svg.replace("<svg ", '<svg role="img" aria-label="QR code for setting up your authenticator app" ', 1)
    return Markup(svg[svg.index("<svg"):])


@router.get("/mfa/setup")
def mfa_setup(request: Request):
    with get_engine().connect() as conn:
        user = _pending(conn, request)
        if user is None:
            return RedirectResponse("/staff/login", status_code=303)
        issuer = config_store.get(conn, "site")["jurisdiction_name"] + " portal"
        uri = auth.totp_uri(user["totp_secret"], user["email"], issuer)
        secret = " ".join(user["totp_secret"][i:i + 4] for i in range(0, len(user["totp_secret"]), 4))
        return render(request, "staff/mfa_setup.html", conn, page_title="Set up two-step sign in", qr=_qr_svg(uri),
                      secret=secret, error=None)


@router.post("/mfa/setup", dependencies=[Depends(verify_csrf)])
async def mfa_setup_submit(request: Request):
    form = await request.form()
    with tx() as conn:
        user = _pending(conn, request)
        if user is None:
            return RedirectResponse("/staff/login", status_code=303)
        if not auth.verify_totp(user["totp_secret"], str(form.get("code", ""))):
            issuer = config_store.get(conn, "site")["jurisdiction_name"] + " portal"
            uri = auth.totp_uri(user["totp_secret"], user["email"], issuer)
            secret = " ".join(user["totp_secret"][i:i + 4] for i in range(0, len(user["totp_secret"]), 4))
            return render(request, "staff/mfa_setup.html", conn, status_code=400, page_title="Set up two-step sign in",
                          qr=_qr_svg(uri), secret=secret,
                          error="That code didn't match. Check the phone's clock is set automatically, then try the newest code.")
        conn.execute(users.update().where(users.c.id == user["id"]).values(mfa_enrolled=True))
        audit(conn, user["email"], "mfa.enrolled", "user", user["email"], ip=client_ip(request))
        user["mfa_enrolled"] = True
        return _finish_login(request, conn, user)


@router.get("/password")
def password_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.current_staff(request, conn)
        if user is None:
            return RedirectResponse("/staff/login", status_code=303)
        return render(request, "staff/password.html", conn, page_title="Choose a new password", errors={},
                      forced=user["must_change_password"])


@router.post("/password", dependencies=[Depends(verify_csrf)])
async def password_submit(request: Request):
    form = await request.form()
    new, confirm, current = str(form.get("new", "")), str(form.get("confirm", "")), str(form.get("current", ""))
    with tx() as conn:
        user = auth.current_staff(request, conn)
        if user is None:
            return RedirectResponse("/staff/login", status_code=303)
        errors = {}
        if auth.is_demo_account(user["email"]):
            flash(request, "The shared demonstration account's password can't be changed.", "warning")
            return RedirectResponse("/staff", status_code=303)
        if not auth.verify_password(user["password_hash"], current):
            errors["current"] = "Your current password isn't right."
        problem = auth.password_problem(new)
        if problem:
            errors["new"] = problem
        elif new != confirm:
            errors["confirm"] = "The two new passwords don't match."
        elif new == current:
            errors["new"] = "Choose a password different from the current one."
        if errors:
            return render(request, "staff/password.html", conn, status_code=400, page_title="Choose a new password",
                          errors=errors, forced=user["must_change_password"])
        conn.execute(users.update().where(users.c.id == user["id"])
                     .values(password_hash=auth.hash_password(new), must_change_password=False))
        audit(conn, user["email"], "password.changed", "user", user["email"], ip=client_ip(request))
    flash(request, "Password changed.")
    return RedirectResponse("/staff", status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(request: Request):
    request.session.clear()
    flash(request, "You are signed out.")
    return RedirectResponse("/staff/login", status_code=303)


@router.post("/ping")
async def ping(request: Request):
    """Keeps a staff session alive when the person chooses 'Stay signed in'."""
    with get_engine().connect() as conn:
        user = auth.current_staff(request, conn)  # refreshes the idle timer
    return JSONResponse({"ok": user is not None})
