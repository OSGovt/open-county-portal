"""Shared web helpers: templates, flash messages, CSRF, money and dates."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup, escape

from . import __version__, config_store
from .db import get_engine, settings_table
from .settings import get_settings

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": True}).enable("table")


def money(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def parse_money(text: str) -> int | None:
    """'$1,234.50' -> 123450. Returns None if it is not an amount."""
    cleaned = (text or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = round(float(cleaned) * 100)
    except ValueError:
        return None
    return value if value >= 0 else None


def markdown(text: str | None) -> Markup:
    return Markup(_md.render(text or ""))


def site_tz(conn=None) -> ZoneInfo:
    try:
        if conn is None:
            with get_engine().connect() as c:
                tzname = config_store.get(c, "site").get("timezone") or "America/Chicago"
        else:
            tzname = config_store.get(conn, "site").get("timezone") or "America/Chicago"
        return ZoneInfo(tzname)
    except Exception:
        return ZoneInfo("America/Chicago")


def local(value: dt.datetime | None, fmt: str = "%B %-d, %Y, %-I:%M %p") -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    out = value.astimezone(site_tz()).strftime(fmt)
    return out.replace("AM", "a.m.").replace("PM", "p.m.")


def longdate(value: dt.date | dt.datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        value = value.astimezone(site_tz()).date() if value.tzinfo else value.date()
    return value.strftime("%B %-d, %Y")


def doclinks(text: str) -> Markup:
    """Turn 'docs/admin/x.md' mentions into links to the built-in Help page."""
    import re as _re
    out = str(escape(text))
    return Markup(_re.sub(r"docs/([a-z0-9_/-]+)\.md", lambda m: f'<a href="/staff/help/{m.group(1)}">the guide</a>', out))


def records_office_name() -> str:
    """The office that keeps land records here (County Clerk, County Recorder, ...)."""
    from sqlalchemy import select
    from .db import offices, services
    try:
        with get_engine().connect() as conn:
            name = conn.execute(select(offices.c.name).select_from(
                services.join(offices, offices.c.slug == services.c.office_slug))
                .where(services.c.slug == "property-records")).scalar()
    except Exception:
        name = None
    return name or "records office"


templates.env.globals["records_office_name"] = records_office_name
templates.env.filters["money"] = money
templates.env.filters["doclinks"] = doclinks
templates.env.filters["markdown"] = markdown
templates.env.filters["localtime"] = local
templates.env.filters["longdate"] = longdate


# ---- flash messages (shown once, announced to screen readers) -------------

def flash(request: Request, message: str, kind: str = "success") -> None:
    request.session.setdefault("_flash", []).append({"message": message, "kind": kind})


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flash", [])


# ---- CSRF ------------------------------------------------------------------

def csrf_token(request: Request) -> str:
    token = request.session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf"] = token
    return token


async def verify_csrf(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    form = await request.form()
    sent = form.get("_csrf") or request.headers.get("x-csrf-token") or ""
    expected = request.session.get("_csrf") or ""
    if not expected or not hmac.compare_digest(str(sent), expected):
        raise HTTPException(status_code=400, detail="This form expired. Go back, reload the page, and try again.")


# ---- page context ------------------------------------------------------------

def theme_version(conn) -> str:
    row = conn.execute(settings_table.select().where(settings_table.c.key == "theme")).first()
    stamp = row.updated_at.isoformat() if row else "default"
    return hashlib.sha256(f"{stamp}{__version__}".encode()).hexdigest()[:10]


def base_context(request: Request, conn) -> dict[str, Any]:
    site = config_store.get(conn, "site")
    theme = config_store.get(conn, "theme") or {}
    return {
        "request": request,
        "site": site,
        "theme": theme,
        "alert": config_store.get(conn, "alert"),
        "theme_version": theme_version(conn),
        "csrf": csrf_token(request),
        "flashes": pop_flashes(request),
        "cart_count": len(request.session.get("cart", [])),
        "version": __version__,
        "site_url": get_settings().site_url,
        "staff_user": request.session.get("staff_name") if request.session.get("staff_mfa_ok") else None,
        "now": dt.datetime.now(dt.timezone.utc),
    }


def render(request: Request, template: str, conn, status_code: int = 200, **ctx: Any) -> HTMLResponse:
    context = base_context(request, conn)
    context.update(ctx)
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
