"""Work queues: certified copies to prepare, public information requests,
and submitted applications."""
from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select

from ... import auth, config_store, images as img, notify, records as rec_mod
from ...db import (applications, audit, certified_copies, files, get_engine, order_lines, orders, pia_requests, tx,
                   utcnow)
from ...settings import get_settings
from ...web import flash, local, verify_csrf
from .common import staff_render

router = APIRouter()

PIA_STATUSES = [("received", "Received"), ("clarification", "Asked the requester to clarify"),
                ("estimate", "Sent a cost estimate"), ("ruling", "Asked the Attorney General for a ruling"),
                ("released", "Released"), ("closed", "Closed")]
APP_STATUSES = [("awaiting_payment", "Waiting for payment"), ("received", "Received"), ("in_review", "In review"),
                ("approved", "Approved"), ("denied", "Denied"), ("completed", "Completed")]


# ---- certified copies --------------------------------------------------------------

@router.get("/orders")
def orders_queue(request: Request, show: str = "pending"):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "records")
        stmt = (select(order_lines, orders.c.number, orders.c.email, orders.c.paid_at)
                .select_from(order_lines.join(orders, orders.c.id == order_lines.c.order_id))
                .where(orders.c.status == "paid", order_lines.c.kind == "certified_copy",
                       order_lines.c.fee_code.is_not(None)))
        if show == "pending":
            stmt = stmt.where(order_lines.c.fulfil_status == "pending")
        rows = conn.execute(stmt.order_by(orders.c.paid_at).limit(300)).mappings().all()
        return staff_render(request, "staff/orders_queue.html", conn, user, page_title="Certified copies", rows=rows,
                            show=show)


@router.post("/orders/{line_id}/issue", dependencies=[Depends(verify_csrf)])
async def issue_certified(request: Request, line_id: int):
    """Generate a certified PDF: certification page + every page image."""
    with tx() as conn:
        user = auth.require(request, conn, "records")
        line = conn.execute(select(order_lines, orders.c.email, orders.c.number.label("order_number"))
                            .select_from(order_lines.join(orders, orders.c.id == order_lines.c.order_id))
                            .where(order_lines.c.id == line_id)).mappings().first()
        if line is None:
            raise HTTPException(404)
        rec = rec_mod.get(conn, line["ref"], include_restricted=True)
        if rec is None:
            raise HTTPException(404, "The instrument for this order no longer exists.")
        site = config_store.get(conn, "site")
        code = secrets.token_hex(5).upper()
        pngs = [img.cached_page(i, rec_mod.marks_for(conn, i["id"])) for i in rec["images"]]
        base = get_settings().site_url
        cover = [f"CERTIFIED COPY: {rec['doc_type']} {rec['instrument_number']}",
                 f"{site['jurisdiction_name']}, {site.get('state_name', '')}",
                 f"I certify that the attached {len(pngs)} page(s) are a true and correct copy of",
                 f"instrument {rec['instrument_number']} as recorded in the official public records.",
                 f"Issued {local(utcnow())} by {user['name']}.",
                 "",
                 f"Verification code: {code}",
                 f"Verify this copy at {base}/verify/{code}"]
        pdf = img.assemble_pdf(pngs, cover)
        digest = hashlib.sha256(pdf).hexdigest()
        rel = f"certified/{rec['instrument_number']}-{code}.pdf"
        dest = get_settings().files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pdf)
        fid = conn.execute(files.insert().values(name=f"{rec['instrument_number']}-certified.pdf", path=rel,
                                                 mime="application/pdf", sha256=digest, bytes=len(pdf))
                           .returning(files.c.id)).scalar_one()
        conn.execute(certified_copies.insert().values(code=code, order_line_id=line_id,
                                                      instrument_number=rec["instrument_number"], file_id=fid,
                                                      sha256=digest, issued_by=user["email"]))
        conn.execute(order_lines.update().where(order_lines.c.order_id == line["order_id"],
                                                order_lines.c.ref == line["ref"],
                                                order_lines.c.kind == "certified_copy").values(fulfil_status="done"))
        audit(conn, user["email"], "certified.issue", "instrument", rec["instrument_number"], {"code": code, "sha256": digest})
    notify.send(line["email"], f"Your certified copy of {line['ref']} is ready",
                f"Download it here: {base}/verify/{code}/download\n\nAnyone can confirm it is genuine at {base}/verify/{code}")
    flash(request, f"Certified copy issued with verification code {code}.")
    return RedirectResponse("/staff/orders", status_code=303)


@router.post("/orders/{line_id}/done", dependencies=[Depends(verify_csrf)])
async def mark_done(request: Request, line_id: int):
    with tx() as conn:
        user = auth.require(request, conn, "records")
        line = conn.execute(select(order_lines).where(order_lines.c.id == line_id)).mappings().first()
        if line is None:
            raise HTTPException(404)
        conn.execute(order_lines.update().where(order_lines.c.order_id == line["order_id"],
                                                order_lines.c.ref == line["ref"],
                                                order_lines.c.kind == "certified_copy").values(fulfil_status="done"))
        audit(conn, user["email"], "certified.paper_done", "instrument", line["ref"])
    flash(request, "Marked as mailed or picked up.")
    return RedirectResponse("/staff/orders", status_code=303)


# ---- public information requests ---------------------------------------------------

@router.get("/pia")
def pia_list(request: Request, status: str = "open"):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "pia")
        stmt = select(pia_requests)
        if status == "open":
            stmt = stmt.where(pia_requests.c.status.notin_(["released", "closed"]))
        rows = conn.execute(stmt.order_by(pia_requests.c.received_at).limit(500)).mappings().all()
        return staff_render(request, "staff/pia_list.html", conn, user, page_title="Public information requests",
                            rows=rows, status=status, labels=dict(PIA_STATUSES))


@router.get("/pia/{number}")
def pia_detail(request: Request, number: str):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "pia")
        r = conn.execute(select(pia_requests).where(pia_requests.c.number == number)).mappings().first()
        if r is None:
            raise HTTPException(404)
        return staff_render(request, "staff/pia_detail.html", conn, user, page_title=number, r=r, statuses=PIA_STATUSES)


@router.post("/pia/{number}", dependencies=[Depends(verify_csrf)])
async def pia_update(request: Request, number: str):
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in dict(PIA_STATUSES):
        raise HTTPException(400)
    with tx() as conn:
        user = auth.require(request, conn, "pia")
        r = conn.execute(select(pia_requests).where(pia_requests.c.number == number)).mappings().first()
        if r is None:
            raise HTTPException(404)
        conn.execute(pia_requests.update().where(pia_requests.c.number == number).values(
            status=status, staff_notes=str(form.get("staff_notes", "")), response=str(form.get("response", "")),
            publish_response=form.get("publish_response") == "on", updated_at=utcnow()))
        audit(conn, user["email"], "pia.update", "pia_request", number, {"status": status})
    if form.get("send") == "on" and r["email"]:
        sent = notify.send(r["email"], f"Your public information request {number}",
                           str(form.get("response", "")) or f"The status of your request is now: {dict(PIA_STATUSES)[status]}.")
        flash(request, "Saved and emailed the requester." if sent else "Saved. Email isn't configured, so nothing was sent.",
              "success" if sent else "warning")
    else:
        flash(request, "Saved.")
    return RedirectResponse(f"/staff/pia/{number}", status_code=303)


# ---- applications ------------------------------------------------------------------

@router.get("/applications")
def app_list(request: Request, status: str = "received", form: str = ""):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "applications")
        stmt = select(applications)
        if status != "all":
            stmt = stmt.where(applications.c.status == status)
        if form:
            stmt = stmt.where(applications.c.form == form)
        rows = conn.execute(stmt.order_by(applications.c.created_at).limit(500)).mappings().all()
        forms = sorted(set(conn.execute(select(applications.c.form).distinct()).scalars()))
        return staff_render(request, "staff/app_list.html", conn, user, page_title="Applications", rows=rows,
                            status=status, form=form, forms=forms, statuses=APP_STATUSES)


@router.get("/applications/{number}")
def app_detail(request: Request, number: str):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "applications")
        a = conn.execute(select(applications).where(applications.c.number == number)).mappings().first()
        if a is None:
            raise HTTPException(404)
        return staff_render(request, "staff/app_detail.html", conn, user, page_title=number, a=a, statuses=APP_STATUSES)


@router.get("/applications/{number}/upload/{index}")
def app_upload(request: Request, number: str, index: int):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "applications")
        a = conn.execute(select(applications).where(applications.c.number == number)).mappings().first()
        if a is None or index >= len(a["uploads"] or []) or not a["uploads"][index].get("path"):
            raise HTTPException(404)
        up = a["uploads"][index]
        with tx() as c2:
            audit(c2, user["email"], "application.view_upload", "application", number, {"field": up["field"]})
    path = (get_settings().uploads_dir / up["path"]).resolve()
    if not str(path).startswith(str(get_settings().uploads_dir.resolve())):
        raise HTTPException(404)
    return FileResponse(path, filename=up["name"])


@router.post("/applications/{number}", dependencies=[Depends(verify_csrf)])
async def app_update(request: Request, number: str):
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in dict(APP_STATUSES):
        raise HTTPException(400)
    with tx() as conn:
        user = auth.require(request, conn, "applications")
        a = conn.execute(select(applications).where(applications.c.number == number)).mappings().first()
        if a is None:
            raise HTTPException(404)
        conn.execute(applications.update().where(applications.c.number == number).values(
            status=status, staff_notes=str(form.get("staff_notes", "")), updated_at=utcnow()))
        audit(conn, user["email"], "application.update", "application", number, {"status": status})
    if form.get("notify") == "on" and a["email"]:
        notify.send(a["email"], f"Update on {number}", f"The status of {number} is now: {dict(APP_STATUSES)[status]}.\n\n"
                    + str(form.get("message", "")))
    flash(request, "Saved.")
    return RedirectResponse(f"/staff/applications/{number}", status_code=303)
