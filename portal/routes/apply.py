"""Applications and requests: state-pack forms (permits, licenses, jury,
vital records) and Public Information Act requests."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.datastructures import UploadFile

from .. import cart as cart_mod, config_store, fees as fee_mod, notify, statepacks
from ..db import applications, audit, get_engine, next_number, offices, pia_requests, tx
from ..settings import get_settings
from ..web import client_ip, flash, render, verify_csrf

router = APIRouter()
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_UPLOADS = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8",
                   ".heic": None, ".webp": b"RIFF", ".tif": None, ".tiff": None}


def forms_available(conn) -> dict[str, dict]:
    site = config_store.get(conn, "site")
    try:
        forms = dict(statepacks.forms_for(site["state"], site["jurisdiction_type"]))
    except statepacks.PackError:
        forms = {}
    forms.update(config_store.get(conn, "forms_custom") or {})
    return forms


def _validate(form_def: dict, data, max_mb: int) -> tuple[dict, dict, dict]:
    values, errors, files = {}, {}, {}
    for f in form_def.get("fields") or []:
        name, ftype, label = f["name"], f.get("type", "text"), f["label"].rstrip("?:.")
        if ftype == "file":
            up = data.get(name)
            if isinstance(up, UploadFile) and up.filename:
                files[name] = up
            elif f.get("required"):
                errors[name] = f"Add a file for: {label.lower()}."
            continue
        if ftype == "checkbox":
            value = data.getlist(name)
        else:
            value = str(data.get(name, "")).strip()
        values[name] = value
        if f.get("required") and not value:
            errors[name] = f"{'Choose' if ftype in ('radio', 'select', 'checkbox') else 'Enter'} {label[0].lower() + label[1:]}."
            continue
        if not value:
            continue
        if ftype == "email" and not EMAIL.match(value):
            errors[name] = "Enter an email address like name@example.com."
        elif ftype == "date":
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                errors[name] = "Enter a date like 2026-03-31."
        elif ftype in ("radio", "select") and value not in [str(o) for o in f.get("options") or []]:
            errors[name] = "Choose one of the listed options."
        elif len(value) > 5000:
            errors[name] = "This answer is too long. Keep it under 5,000 characters."
    return values, errors, files


async def _save_uploads(files: dict, number: str, form_def: dict, max_mb: int) -> tuple[list[dict], dict]:
    saved, errors = [], {}
    base = get_settings().uploads_dir / dt.date.today().strftime("%Y/%m") / number
    sensitive = {f["name"] for f in form_def.get("fields") or [] if f.get("sensitive")}
    for name, up in files.items():
        ext = Path(up.filename).suffix.lower()
        if ext not in ALLOWED_UPLOADS:
            errors[name] = "Upload a PDF or a photo (JPG, PNG, HEIC, WEBP or TIFF)."
            continue
        content = await up.read()
        if len(content) > max_mb * 1024 * 1024:
            errors[name] = f"This file is larger than {max_mb} MB. Take a smaller photo or scan at a lower resolution."
            continue
        magic = ALLOWED_UPLOADS[ext]
        if magic and not content.startswith(magic):
            errors[name] = "This file doesn't look like the type its name says. Try saving it again as PDF or JPG."
            continue
        base.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(up.filename).name)[-80:]
        path = base / f"{name}-{safe}"
        path.write_bytes(content)
        saved.append({"field": name, "path": str(path.relative_to(get_settings().uploads_dir)), "name": safe,
                      "bytes": len(content), "sensitive": name in sensitive})
    return saved, errors


@router.get("/apply/{slug}", include_in_schema=False)
def form_page(request: Request, slug: str):
    with get_engine().connect() as conn:
        form_def = forms_available(conn).get(slug)
        if form_def is None:
            raise HTTPException(404)
        fee = fee_mod.current(conn, form_def["fee_code"]) if form_def.get("fee_code") else None
        return render(request, "public/apply.html", conn, page_title=form_def["title"], slug=slug, form_def=form_def,
                      fee=fee, values={}, errors={})


@router.post("/apply/{slug}", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def form_submit(request: Request, slug: str):
    data = await request.form()
    settings = get_settings()
    with get_engine().connect() as conn:
        form_def = forms_available(conn).get(slug)
        if form_def is None:
            raise HTTPException(404)
        fee = fee_mod.current(conn, form_def["fee_code"]) if form_def.get("fee_code") else None
    values, errors, files = _validate(form_def, data, settings.upload_max_mb)
    if not errors:
        with tx() as conn:
            number = next_number(conn, "application", "AP")
        saved, upload_errors = await _save_uploads(files, number, form_def, settings.upload_max_mb)
        errors.update(upload_errors)
    if errors:
        with get_engine().connect() as conn:
            return render(request, "public/apply.html", conn, status_code=400, page_title=form_def["title"], slug=slug,
                          form_def=form_def, fee=fee, values=values, errors=errors)
    email = values.get("email") or next((v for k, v in values.items() if "email" in k), None)
    needs_payment = fee is not None and fee["amount_cents"] > 0
    with tx() as conn:
        conn.execute(applications.insert().values(number=number, form=slug, office_slug=form_def.get("office"),
                                                  data=values, uploads=saved, email=email,
                                                  status="awaiting_payment" if needs_payment else "received"))
        audit(conn, None, "application.submit", "application", number, {"form": slug}, ip=client_ip(request))
    if needs_payment:
        cart_mod.add(request.session, cart_mod.new_item(kind="application", application=number, fee_code=fee["code"]))
        flash(request, f"Application {number} saved. Pay the fee to finish submitting it.")
        return RedirectResponse("/cart", status_code=303)
    notify.send(email, f"We received your {form_def['title'].lower()} ({number})",
                f"Your reference number is {number}. Staff will contact you if they need anything else.")
    with get_engine().connect() as conn:
        return render(request, "public/apply_done.html", conn, page_title="Received", number=number, form_def=form_def)


# ---- Public Information Act ----------------------------------------------------

def _pia_context(conn):
    site = config_store.get(conn, "site")
    try:
        law = statepacks.load(site["state"]).get("public_information", {})
    except statepacks.PackError:
        law = {}
    office_rows = conn.execute(select(offices.c.slug, offices.c.name).where(offices.c.active.is_(True))
                               .order_by(offices.c.sort)).all()
    return law, office_rows


@router.get("/public-information", include_in_schema=False)
def pia_page(request: Request):
    with get_engine().connect() as conn:
        law, office_rows = _pia_context(conn)
        return render(request, "public/pia.html", conn, page_title="Request public information", law=law,
                      office_rows=office_rows, values={}, errors={})


@router.post("/public-information", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def pia_submit(request: Request):
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in ("office_slug", "description", "delivery", "name", "email", "phone")}
    errors = {}
    if not values["description"]:
        errors["description"] = "Describe the records you want."
    if values["delivery"] not in ("email", "mail", "inspect"):
        errors["delivery"] = "Choose how you want to receive the records."
    if values["delivery"] == "email" and not EMAIL.match(values["email"]):
        errors["email"] = "Enter the email address where we should send the records."
    if not values["email"] and not values["phone"]:
        errors.setdefault("email", "Give an email address or phone number so the office can reach you.")
    with tx() as conn:
        law, office_rows = _pia_context(conn)
        if errors:
            return render(request, "public/pia.html", conn, status_code=400, page_title="Request public information",
                          law=law, office_rows=office_rows, values=values, errors=errors)
        number = next_number(conn, "pia", "PIR")
        conn.execute(pia_requests.insert().values(number=number, office_slug=values["office_slug"] or None,
                                                  description=values["description"], delivery=values["delivery"],
                                                  name=values["name"] or None, email=values["email"] or None,
                                                  phone=values["phone"] or None))
        audit(conn, None, "pia.submit", "pia_request", number, ip=client_ip(request))
    notify.send(values["email"], f"Public information request {number} received",
                f"We received your request {number} on {dt.date.today():%B %d, %Y}.\n\n{law.get('response_rule', '')}")
    with get_engine().connect() as conn:
        return render(request, "public/pia_done.html", conn, page_title="Request received", number=number, law=law)


@router.get("/public-information/archive", include_in_schema=False)
def pia_archive(request: Request):
    with get_engine().connect() as conn:
        rows = conn.execute(select(pia_requests).where(pia_requests.c.publish_response.is_(True))
                            .order_by(pia_requests.c.received_at.desc()).limit(200)).mappings().all()
        return render(request, "public/pia_archive.html", conn, page_title="Released public information", rows=rows)
