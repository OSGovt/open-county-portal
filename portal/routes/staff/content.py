"""Content editing: pages, services, offices, meetings, notices, redirects,
files, and the fee schedule."""
from __future__ import annotations

import datetime as dt
import hashlib
import mimetypes
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.datastructures import UploadFile

from ... import auth, config_store, fees as fee_mod, statepacks
from ...db import (audit, fees, files, get_engine, meetings, offices, pages, postings, redirects, services, tombstone,
                   tx, utcnow)
from ...settings import get_settings
from ...web import flash, parse_money, verify_csrf
from .common import staff_render

router = APIRouter(prefix="/content")
SLUG = re.compile(r"^[a-z0-9][a-z0-9/-]*$")


def _office_options(conn):
    return [("", "None")] + [(r.slug, r.name) for r in conn.execute(select(offices.c.slug, offices.c.name).order_by(offices.c.sort))]


def _rule_options(conn):
    site = config_store.get(conn, "site")
    try:
        rules = statepacks.posting_rules(site["state"], site["jurisdiction_type"])
    except statepacks.PackError:
        rules = []
    return [("", "Not a required posting")] + [(r["code"], f"{r['title']} ({r['authority']})") for r in rules if not r.get("automatic")]


ENTITIES: dict[str, dict] = {
    "pages": {"table": pages, "title": "Pages", "one": "page", "key": "id", "deletable": True, "public": "/pages/{slug}",
              "list": ["title", "slug", "published", "updated_at"],
              "fields": [("title", "Title", "text", True, ""), ("slug", "Web address", "slug", True,
                          "Lowercase words joined by hyphens. The page appears at /pages/your-words."),
                         ("body", "Content", "markdown", False, ""), ("published", "Published", "bool", False,
                          "Unpublished pages are only visible here."),
                         ("review_note", "Review note (staff only)", "textarea", False, "")]},
    "services": {"table": services, "title": "Services", "one": "service", "key": "id", "deletable": False,
                 "public": "/services/{slug}", "list": ["title", "category", "featured", "published"],
                 "fields": [("title", "Title", "text", True, "Start with a verb: \"Pay property tax\""),
                            ("slug", "Web address", "slug", True, ""), ("office_slug", "Office", "office", False, ""),
                            ("category", "Category", "text", False, "Groups services on the Services page."),
                            ("summary", "One-sentence summary", "text", False, ""),
                            ("who", "Who can do this", "markdown", False, ""), ("needs", "What you need", "markdown", False, ""),
                            ("cost", "Cost", "markdown", False, "Name the fee; amounts come from the fee schedule."),
                            ("timing", "How long it takes", "markdown", False, ""),
                            ("online_label", "Online button text", "text", False, ""),
                            ("online_target", "Online button goes to", "text", False,
                             "A page on this site like /records, or a full https:// address for another agency."),
                            ("handoff", "The button leaves this site", "bool", False, "Residents are told they are leaving."),
                            ("in_person", "Doing it in person", "markdown", False, ""),
                            ("body", "More information", "markdown", False, ""), ("keywords", "Search words", "text", False,
                             "Words people might search for, separated by spaces."),
                            ("featured", "Show on the home page", "bool", False, ""), ("published", "Published", "bool", False, ""),
                            ("sort", "Order", "int", False, "Lower numbers appear first.")]},
    "offices": {"table": offices, "title": "Offices", "one": "office", "key": "id", "deletable": False,
                "public": "/offices/{slug}", "list": ["name", "official", "phone", "active"],
                "fields": [("name", "Office name", "text", True, ""), ("slug", "Web address", "slug", True, ""),
                           ("official", "Elected official or head", "text", False, ""),
                           ("description", "What the office does", "markdown", False, ""),
                           ("phone", "Phone", "text", False, ""), ("email", "Email", "text", False, ""),
                           ("address", "Address", "textarea", False, ""), ("hours", "Hours", "textarea", False, ""),
                           ("merchant_account", "Payment processor merchant account (staff only)", "text", False,
                            "Used to send this office's share of each payment to its own account."),
                           ("sort", "Order", "int", False, ""), ("active", "Active", "bool", False, "")]},
    "meetings": {"table": meetings, "title": "Meetings", "one": "meeting", "key": "id", "deletable": True,
                 "public": "/meetings/{id}", "list": ["title", "starts_at", "status"],
                 "fields": [("body", "Governing body", "text", True, "For example: Commissioners Court"),
                            ("title", "Meeting title", "text", True, "For example: Regular meeting"),
                            ("starts_at", "Date and time", "datetime", True, "Local time."),
                            ("location", "Location", "text", False, ""), ("agenda", "Agenda", "markdown", False,
                             "Number each item. Attach documents as links."),
                            ("status", "Status", "select:draft=Draft (not public),posted=Posted (public),held=Held,cancelled=Cancelled",
                             True, "Choosing Posted publishes the notice and agenda and records the posting time."),
                            ("video_url", "Video link", "text", False, "Use a captioned video."),
                            ("minutes", "Approved minutes", "markdown", False, "")]},
    "postings": {"table": postings, "title": "Notices", "one": "notice", "key": "id", "deletable": True,
                 "public": "/notices", "list": ["title", "rule_code", "posted_at", "published"],
                 "fields": [("title", "Title", "text", True, ""), ("rule_code", "Required by", "rule", False,
                             "Choosing the requirement lets the dashboard confirm it was posted."),
                            ("body", "Text of the notice", "markdown", False, ""),
                            ("upload", "Attach a document", "file", False, "Prefer an accessible PDF or a Word file."),
                            ("office_slug", "Office", "office", False, ""),
                            ("remove_after", "Take down after", "date", False, "Leave blank to keep it posted."),
                            ("published", "Published", "bool", False, "")]},
    "redirects": {"table": redirects, "title": "Redirects", "one": "redirect", "key": "old_path", "deletable": True,
                  "public": None, "list": ["old_path", "new_path"],
                  "fields": [("old_path", "Old address (path only)", "text", True, "For example: /departments/clerk.html"),
                             ("new_path", "New address", "text", True, "For example: /offices/county-clerk")]},
}


def _ent(name: str) -> dict:
    if name not in ENTITIES:
        raise HTTPException(404)
    return ENTITIES[name]


def _tz(conn) -> ZoneInfo:
    return ZoneInfo(config_store.get(conn, "site").get("timezone") or "America/Chicago")


@router.get("")
def index(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "content")
        return staff_render(request, "staff/content_index.html", conn, user, page_title="Content", entities=ENTITIES,
                            draft_pages=conn.execute(select(pages).where(pages.c.published.is_(False))
                                                     .order_by(pages.c.title).limit(100)).mappings().all())


# ---- fees (registered before the generic routes so /content/fees is not treated as an entity) ---------

@router.get("/fees")
def fee_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin", "finance")
        names = {r.slug: r.name for r in conn.execute(select(offices.c.slug, offices.c.name))}
        return staff_render(request, "staff/fees.html", conn, user, page_title="Fee schedule",
                            current=fee_mod.all_current(conn), upcoming=fee_mod.scheduled(conn), names=names,
                            offices=_office_options(conn)[1:])


@router.post("/fees", dependencies=[Depends(verify_csrf)])
async def fee_action(request: Request):
    form = await request.form()
    action = form.get("action")
    with tx() as conn:
        user = auth.require(request, conn, "admin", "finance")
        if action == "confirm":
            fid = int(form.get("fee_id", 0))
            adopted = str(form.get("adopted_by", "")).strip()
            if not adopted:
                flash(request, "Enter the order or resolution that adopted this fee (for example: Court Order 2026-114).", "error")
                return RedirectResponse("/staff/content/fees", status_code=303)
            conn.execute(fees.update().where(fees.c.id == fid).values(confirmed=True, confirmed_by=user["email"],
                                                                      adopted_by=adopted))
            audit(conn, user["email"], "fee.confirm", "fee", fid, {"adopted_by": adopted})
            flash(request, "Fee confirmed.")
        elif action in ("schedule", "new"):
            code = str(form.get("code", "")).strip()
            amount = parse_money(str(form.get("amount", "")))
            try:
                start = dt.date.fromisoformat(str(form.get("effective_from", "")))
            except ValueError:
                start = None
            adopted = str(form.get("adopted_by", "")).strip()
            errors = []
            if not re.match(r"^[a-z0-9_]+$", code):
                errors.append("Fee code: use lowercase letters, numbers and underscores.")
            if amount is None:
                errors.append("Enter the amount, like 25.00.")
            if start is None:
                errors.append("Enter the date the fee takes effect.")
            if not adopted:
                errors.append("Enter the order or resolution that adopted the fee.")
            if errors:
                flash(request, " ".join(errors), "error")
                return RedirectResponse("/staff/content/fees", status_code=303)
            existing = fee_mod.current(conn, code, on=start) or fee_mod.current(conn, code)
            if action == "schedule" and existing is None:
                flash(request, "That fee code doesn't exist. Use 'Add a new fee' instead.", "error")
                return RedirectResponse("/staff/content/fees", status_code=303)
            if action == "new" and existing is not None:
                flash(request, "That fee code already exists. Use 'Schedule a change' instead.", "error")
                return RedirectResponse("/staff/content/fees", status_code=303)
            base = existing or {}
            if existing:
                conn.execute(fees.update().where(fees.c.id == existing["id"])
                             .values(effective_to=start - dt.timedelta(days=1)))
            conn.execute(fees.insert().values(
                code=code, office_slug=str(form.get("office_slug") or base.get("office_slug") or ""),
                label=str(form.get("label") or base.get("label") or code), amount_cents=amount,
                unit=str(form.get("unit") or base.get("unit") or "each"),
                statute=str(form.get("statute") or base.get("statute") or ""),
                fund=str(form.get("fund") or base.get("fund") or "General Fund"), effective_from=start,
                adopted_by=adopted, confirmed=True, confirmed_by=user["email"], counter=True))
            audit(conn, user["email"], f"fee.{action}", "fee", code, {"amount_cents": amount, "from": start.isoformat(),
                                                                       "adopted_by": adopted})
            flash(request, f"Fee {code} set to ${amount / 100:.2f} starting {start:%B %d, %Y}.")
    return RedirectResponse("/staff/content/fees", status_code=303)


# ---- generic list / edit -------------------------------------------------------

@router.get("/{entity}")
def list_rows(request: Request, entity: str):
    ent = _ent(entity)
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "content")
        t = ent["table"]
        order = t.c.sort if "sort" in t.c else (t.c.starts_at.desc() if "starts_at" in t.c else list(t.c)[0])
        rows = conn.execute(select(t).order_by(order).limit(1000)).mappings().all()
        return staff_render(request, "staff/content_list.html", conn, user, page_title=ent["title"], ent=ent,
                            entity=entity, rows=rows)


def _form_fields(conn, ent):
    out = []
    for name, label, ftype, required, hint in ent["fields"]:
        options = None
        if ftype == "office":
            options, ftype = _office_options(conn), "select"
        elif ftype == "rule":
            options, ftype = _rule_options(conn), "select"
        elif ftype.startswith("select:"):
            options = [tuple(o.split("=", 1)) for o in ftype[7:].split(",")]
            ftype = "select"
        out.append({"name": name, "label": label, "type": ftype, "required": required, "hint": hint, "options": options})
    return out


@router.get("/{entity}/new")
def new_row(request: Request, entity: str):
    ent = _ent(entity)
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "content")
        defaults = {"published": True, "active": True, "status": "draft", "sort": 100}
        return staff_render(request, "staff/content_edit.html", conn, user, page_title=f"New {ent['one']}", ent=ent,
                            entity=entity, row=defaults, key=None, fields=_form_fields(conn, ent), errors={})


@router.get("/{entity}/{key:path}/edit")
def edit_row(request: Request, entity: str, key: str):
    ent = _ent(entity)
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "content")
        t = ent["table"]
        col = t.c[ent["key"]]
        row = conn.execute(select(t).where(col == (int(key) if ent["key"] == "id" else key))).mappings().first()
        if row is None:
            raise HTTPException(404)
        row = dict(row)
        if row.get("starts_at"):
            row["starts_at"] = row["starts_at"].astimezone(_tz(conn)).strftime("%Y-%m-%dT%H:%M")
        return staff_render(request, "staff/content_edit.html", conn, user, page_title=f"Edit {ent['one']}", ent=ent,
                            entity=entity, row=row, key=key, fields=_form_fields(conn, ent), errors={})


async def _save_file(up: UploadFile, actor: str) -> dict:
    content = await up.read()
    if len(content) > 50 * 1024 * 1024:
        raise ValueError("Files must be under 50 MB.")
    digest = hashlib.sha256(content).hexdigest()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(up.filename).name)[-100:]
    rel = Path(dt.date.today().strftime("%Y/%m")) / f"{digest[:12]}-{safe}"
    dest = get_settings().files_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    mime = mimetypes.guess_type(safe)[0] or "application/octet-stream"
    return {"name": safe, "path": str(rel), "mime": mime, "sha256": digest, "bytes": len(content),
            "needs_accessibility_review": mime == "application/pdf"}


@router.post("/{entity}/save", dependencies=[Depends(verify_csrf)])
async def save_row(request: Request, entity: str):
    ent = _ent(entity)
    form = await request.form()
    key = form.get("_key") or None
    with tx() as conn:
        user = auth.require(request, conn, "content")
        fields = _form_fields(conn, ent)
        values, errors = {}, {}
        for f in fields:
            name, ftype = f["name"], f["type"]
            if ftype == "file":
                up = form.get(name)
                if isinstance(up, UploadFile) and up.filename:
                    try:
                        meta = await _save_file(up, user["email"])
                    except ValueError as exc:
                        errors[name] = str(exc)
                        continue
                    values["file_id"] = conn.execute(files.insert().values(**meta).returning(files.c.id)).scalar_one()
                continue
            raw = form.get(name)
            if ftype == "bool":
                values[name] = raw == "on"
                continue
            raw = (str(raw) if raw is not None else "").strip()
            if f["required"] and not raw:
                errors[name] = f"Enter {f['label'].lower()}."
                continue
            if ftype == "slug" and raw and not SLUG.match(raw):
                errors[name] = "Use lowercase letters, numbers and hyphens only."
            elif ftype == "int":
                values[name] = int(raw) if raw.lstrip("-").isdigit() else 100
                continue
            elif ftype == "date":
                try:
                    values[name] = dt.date.fromisoformat(raw) if raw else None
                except ValueError:
                    errors[name] = "Enter a date like 2026-12-31."
                continue
            elif ftype == "datetime":
                try:
                    values[name] = dt.datetime.fromisoformat(raw).replace(tzinfo=_tz(conn))
                except ValueError:
                    errors[name] = "Enter a date and time."
                continue
            values[name] = raw or None
        if entity == "redirects":
            for k in ("old_path", "new_path"):
                if values.get(k) and not str(values[k]).startswith("/"):
                    errors[k] = "Start with a slash, like /old-page.html"
        kcol = ent["key"]
        if not key and kcol != "id" and values.get(kcol) and kcol not in errors:
            t0 = ent["table"]
            if conn.execute(select(t0.c[kcol]).where(t0.c[kcol] == values[kcol])).first():
                label = next((f["label"] for f in fields if f["name"] == kcol), kcol).lower()
                errors[kcol] = f"There's already a {ent['one']} with this {label}. Edit that one instead."
        if errors:
            row = dict(values)
            return staff_render(request, "staff/content_edit.html", conn, user, status_code=400,
                                page_title=f"{'Edit' if key else 'New'} {ent['one']}", ent=ent, entity=entity, row=row,
                                key=key, fields=fields, errors=errors)
        t = ent["table"]
        if entity == "meetings" and values.get("status") == "posted":
            existing = conn.execute(select(meetings.c.posted_at).where(meetings.c.id == int(key))).scalar() if key else None
            values["posted_at"] = existing or utcnow()
        if "updated_at" in t.c:
            values["updated_at"] = utcnow()
        if key:
            col = t.c[ent["key"]]
            conn.execute(t.update().where(col == (int(key) if ent["key"] == "id" else key)).values(**values))
        else:
            conn.execute(t.insert().values(**values))
        audit(conn, user["email"], f"{entity}.save", entity, key or values.get("slug") or values.get("title"))
    flash(request, f"Saved the {ent['one']}.")
    return RedirectResponse(f"/staff/content/{entity}", status_code=303)


@router.post("/{entity}/{key:path}/delete", dependencies=[Depends(verify_csrf)])
async def delete_row(request: Request, entity: str, key: str):
    ent = _ent(entity)
    if not ent["deletable"]:
        raise HTTPException(400, "This kind of item can be unpublished but not deleted.")
    with tx() as conn:
        user = auth.require(request, conn, "content")
        t = ent["table"]
        col = t.c[ent["key"]]
        conn.execute(t.delete().where(col == (int(key) if ent["key"] == "id" else key)))
        tombstone(conn, ent["one"], key)
        audit(conn, user["email"], f"{entity}.delete", entity, key)
    flash(request, f"Deleted the {ent['one']}.")
    return RedirectResponse(f"/staff/content/{entity}", status_code=303)
