"""System: go-live checklist, imports, backups, audit log, built-in help."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from markupsafe import Markup
from sqlalchemy import func, select

from ... import __version__, auth, compliance, config_store, fees as fee_mod, notify, ops, ops_status, payments
from ...db import audit, audit_log, get_engine, import_batches, schema_version, tx, users
from ...settings import get_settings
from ...web import flash, markdown, verify_csrf
from .common import staff_render

router = APIRouter()
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"

MANUAL_CHECKS = [
    ("a11y_manual", "Someone tested the main tasks with only a keyboard and with a screen reader (docs/admin/accessibility-testing.md)."),
    ("fees_signed", "The clerk or finance office reviewed every fee against the adopted fee order."),
    ("staff_trained", "Every office's staff practiced their tasks with sample data."),
    ("content_reviewed", "Each office reviewed its service and office pages."),
    ("records_signed", "The County Clerk signed off on the records import report."),
    ("datagov", "The Data.gov harvest request was submitted (docs/admin/data-gov.md)."),
    ("offsite_backup", "Backups are copied off the server, and a restore was practiced."),
    ("cutover_plan", "The cutover plan and the way back were reviewed (docs/admin/cutover.md)."),
]


def _auto_checks(conn) -> list[tuple[str, bool, str]]:
    site = config_store.get(conn, "site")
    od = config_store.get(conn, "open_data")
    policy = config_store.get(conn, "payments")
    status = ops_status.summary()
    demo_loaded = conn.execute(select(import_batches.c.id).where(import_batches.c.source == "demo-sample-data",
                                                                 import_batches.c.status != "undone")).first() is not None
    pending_imports = conn.execute(select(func.count()).select_from(import_batches)
                                   .where(import_batches.c.status == "loaded", import_batches.c.kind != "demo")).scalar_one()
    no_mfa = conn.execute(select(func.count()).select_from(users)
                          .where(users.c.active.is_(True), users.c.mfa_enrolled.is_(False))).scalar_one()
    postings_bad = [p for p in compliance.check_postings(conn) if p["status"] == "bad"]
    try:
        processor = payments.get(policy.get("processor") or "test")
    except KeyError:
        processor = None
    return [
        ("Sample data removed", not demo_loaded, "Run: sudo countyctl app demo --remove"),
        ("All fees confirmed against the adopted fee order", fee_mod.unconfirmed_count(conn) == 0, "Content, Fee schedule"),
        ("A real payment processor is connected (or pay-at-office is chosen on purpose)",
         processor is not None and not processor.is_test, "Settings, Payments"),
        ("Outgoing email works", notify.configured(), "Set the SMTP lines in /opt/county-portal/.env, then: sudo countyctl restart"),
        ("Site name, address, phone and accessibility contact are filled in",
         all(site.get(k) for k in ("jurisdiction_name", "address", "phone", "accessibility_contact")), "Settings, Site identity"),
        ("Open data contact email is set (Data.gov requires one)", bool(od.get("contact_email") or site.get("email")),
         "Settings, Payments, records and open data"),
        ("Every staff account has its phone code set up", no_mfa == 0, f"{no_mfa} account(s) still need to sign in once"),
        ("A backup finished in the last 24 hours", status["backup_age_days"] is not None and status["backup_age_days"] < 1,
         "Run: sudo countyctl backup"),
        ("Bulk open data files have been generated", bool(status["bulk_generated_at"]), "Run: sudo countyctl app export-bulk"),
        ("No required postings are missing", not postings_bad, f"{len(postings_bad)} missing; see the dashboard"),
        ("Every records import has been signed off", pending_imports == 0, "System, Imports"),
        ("The site uses HTTPS", get_settings().site_url.startswith("https://"), "Set PORTAL_SITE_URL and the host name at install"),
    ]


@router.get("/system")
def system_home(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        backups = [{"name": b.name, "manifest": (b / "manifest.json").read_text()[:2000]} for b in ops.list_backups()[:20]]
        return staff_render(request, "staff/system.html", conn, user, page_title="System", version=__version__,
                            schema=schema_version(conn), status=ops_status.summary(), backups=backups)


@router.post("/system/backup", dependencies=[Depends(verify_csrf)])
async def backup_now(request: Request, background: BackgroundTasks):
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        audit(conn, user["email"], "backup.request")
    background.add_task(ops.backup, "manual", None, lambda m: None)
    flash(request, "A backup has started. Refresh this page in a few minutes to see it listed.")
    return RedirectResponse("/staff/system", status_code=303)


@router.get("/system/golive")
def golive(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        checked = set(config_store.get(conn, "golive").get("checked") or [])
        auto = _auto_checks(conn)
        ready = all(ok for _, ok, _ in auto) and all(k in checked for k, _ in MANUAL_CHECKS)
        return staff_render(request, "staff/golive.html", conn, user, page_title="Go-live checklist", auto=auto,
                            manual=MANUAL_CHECKS, checked=checked, ready=ready)


@router.post("/system/golive", dependencies=[Depends(verify_csrf)])
async def golive_save(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        checked = [k for k, _ in MANUAL_CHECKS if form.get(k) == "on"]
        config_store.put(conn, "golive", {"checked": checked}, actor=user["email"])
        audit(conn, user["email"], "golive.update", detail={"checked": checked})
    flash(request, "Checklist saved.")
    return RedirectResponse("/staff/system/golive", status_code=303)


@router.get("/system/migrations")
def migrations(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        rows = conn.execute(select(import_batches).order_by(import_batches.c.id.desc())).mappings().all()
        return staff_render(request, "staff/migrations.html", conn, user, page_title="Imports", rows=rows)


@router.get("/system/migrations/{batch_id}/report")
def migration_report(request: Request, batch_id: int):
    with get_engine().connect() as conn:
        auth.require(request, conn, "admin", "records")
        b = conn.execute(select(import_batches).where(import_batches.c.id == batch_id)).mappings().first()
    if b is None or not b["report_path"]:
        raise HTTPException(404, "No verification report yet. Run: sudo countyctl app migrate records verify --batch "
                                 f"{batch_id}")
    path = Path(b["report_path"])
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="text/html")


@router.post("/system/migrations/{batch_id}/signoff", dependencies=[Depends(verify_csrf)])
async def migration_signoff(request: Request, batch_id: int):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    with tx() as conn:
        user = auth.require(request, conn, "admin", "records")
        if not name:
            flash(request, "Type the name and title of the person signing off.", "error")
            return RedirectResponse("/staff/system/migrations", status_code=303)
        conn.execute(import_batches.update().where(import_batches.c.id == batch_id)
                     .values(status="verified", signed_off_by=f"{name} ({user['email']}, {dt.date.today()})"))
        audit(conn, user["email"], "import.signoff", "import_batch", batch_id, {"name": name})
    flash(request, "Import signed off.")
    return RedirectResponse("/staff/system/migrations", status_code=303)


@router.get("/system/audit")
def audit_view(request: Request, actor: str = "", action: str = "", page: int = 1):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        stmt = select(audit_log)
        if actor:
            stmt = stmt.where(audit_log.c.actor.ilike(f"%{actor}%"))
        if action:
            stmt = stmt.where(audit_log.c.action.ilike(f"{action}%"))
        rows = conn.execute(stmt.order_by(audit_log.c.id.desc()).limit(100).offset((max(1, page) - 1) * 100)).mappings().all()
        return staff_render(request, "staff/audit.html", conn, user, page_title="Audit log", rows=rows, actor=actor,
                            action=action, page=page)


@router.get("/help")
@router.get("/help/{path:path}")
def help_page(request: Request, path: str = "admin/README"):
    with get_engine().connect() as conn:
        user = auth.require(request, conn)
        safe = (DOCS_DIR / f"{path.removesuffix('.md')}.md").resolve()
        if not str(safe).startswith(str(DOCS_DIR)) or not safe.exists():
            raise HTTPException(404, "That help page doesn't exist.")
        text = safe.read_text(encoding="utf-8")
        # Keep links between help pages working inside the console.
        import re
        text = re.sub(r"\]\((?!https?://)([^)#]+)\.md(#[^)]*)?\)",
                      lambda m: f"](/staff/help/{(safe.parent.relative_to(DOCS_DIR) / m.group(1)).as_posix()}{m.group(2) or ''})",
                      text)
        return staff_render(request, "staff/help.html", conn, user, page_title="Help", body=markdown(text), path=path)
