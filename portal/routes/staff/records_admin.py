"""Records administration: index corrections, restricting records,
redaction requests and the page redaction tool."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import or_, select

from ... import auth, images as img, records as rec_mod
from ...db import (audit, get_engine, images, instruments, parties, redaction_marks, redaction_requests, tx, utcnow)
from ...settings import get_settings
from ...web import flash, verify_csrf
from .common import staff_render

router = APIRouter(prefix="/records")
RR_STATUSES = [("received", "Received"), ("approved", "Approved"), ("applied", "Redactions applied"),
               ("denied", "Denied"), ("rescinded", "Rescinded by requester")]


@router.get("")
def records_home(request: Request, q: str = ""):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "records")
        rows = []
        if q.strip():
            norm = rec_mod.normalize_name(q)
            rows = conn.execute(select(instruments).where(or_(
                instruments.c.instrument_number.ilike(f"{q.strip()}%"),
                instruments.c.id.in_(select(parties.c.instrument_id).where(parties.c.name_norm.like(f"%{norm}%")))))
                .order_by(instruments.c.recorded_date.desc()).limit(100)).mappings().all()
        return staff_render(request, "staff/records_home.html", conn, user, page_title="Records", q=q, rows=rows)


@router.get("/redactions")
def redaction_list(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "records")
        rows = conn.execute(select(redaction_requests).order_by(redaction_requests.c.received_at.desc()).limit(300)).mappings().all()
        return staff_render(request, "staff/redactions.html", conn, user, page_title="Redaction requests", rows=rows,
                            labels=dict(RR_STATUSES))


@router.get("/redactions/{number}")
def redaction_detail(request: Request, number: str):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "records")
        r = conn.execute(select(redaction_requests).where(redaction_requests.c.number == number)).mappings().first()
        if r is None:
            raise HTTPException(404)
        matches = []
        for name in (r["search_names"] or "").splitlines():
            if name.strip():
                found, _ = rec_mod.search(conn, rec_mod.Query(name=name.strip()), page_size=50)
                matches += [m for m in found if m["instrument_number"] not in {x["instrument_number"] for x in matches}]
        marks = conn.execute(select(redaction_marks).where(redaction_marks.c.request_id == r["id"])).mappings().all()
        return staff_render(request, "staff/redaction_detail.html", conn, user, page_title=number, r=r, matches=matches,
                            statuses=RR_STATUSES, marks=marks)


@router.post("/redactions/{number}", dependencies=[Depends(verify_csrf)])
async def redaction_update(request: Request, number: str):
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in dict(RR_STATUSES):
        raise HTTPException(400)
    with tx() as conn:
        user = auth.require(request, conn, "records")
        conn.execute(redaction_requests.update().where(redaction_requests.c.number == number).values(
            status=status, notes=str(form.get("notes", "")), decided_at=utcnow(), decided_by=user["email"]))
        if status == "rescinded":
            rid = conn.execute(select(redaction_requests.c.id).where(redaction_requests.c.number == number)).scalar_one()
            image_ids = list(conn.execute(select(redaction_marks.c.image_id).where(redaction_marks.c.request_id == rid)).scalars())
            conn.execute(redaction_marks.delete().where(redaction_marks.c.request_id == rid))
            _refresh_flags(conn, image_ids)
        audit(conn, user["email"], "redaction.decide", "redaction_request", number, {"status": status})
    flash(request, "Saved.")
    return RedirectResponse(f"/staff/records/redactions/{number}", status_code=303)


def _refresh_flags(conn, image_ids):
    for iid in set(image_ids):
        has = conn.execute(select(redaction_marks.c.id).where(redaction_marks.c.image_id == iid).limit(1)).first() is not None
        conn.execute(images.update().where(images.c.id == iid).values(redacted=has, public_text=None, updated_at=utcnow()))
        inst = conn.execute(select(images.c.instrument_id).where(images.c.id == iid)).scalar()
        conn.execute(instruments.update().where(instruments.c.id == inst).values(updated_at=utcnow()))


@router.get("/{number}")
def record_admin(request: Request, number: str):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "records")
        r = rec_mod.get(conn, number, include_restricted=True)
        if r is None:
            raise HTTPException(404)
        return staff_render(request, "staff/record_admin.html", conn, user, page_title=number, r=r)


@router.post("/{number}", dependencies=[Depends(verify_csrf)])
async def record_save(request: Request, number: str):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "records")
        r = rec_mod.get(conn, number, include_restricted=True)
        if r is None:
            raise HTTPException(404)
        status = "restricted" if form.get("status") == "restricted" else "public"
        conn.execute(instruments.update().where(instruments.c.id == r["id"]).values(
            doc_type=str(form.get("doc_type", r["doc_type"])).strip() or r["doc_type"],
            legal_description=str(form.get("legal_description", "")).strip() or None,
            property_id=str(form.get("property_id", "")).strip() or None,
            remarks=str(form.get("remarks", "")).strip() or None, status=status, updated_at=utcnow()))
        conn.execute(parties.delete().where(parties.c.instrument_id == r["id"]))
        for role in ("grantor", "grantee"):
            for name in str(form.get(role + "s", "")).splitlines():
                if name.strip():
                    conn.execute(parties.insert().values(instrument_id=r["id"], role=role, name=name.strip(),
                                                         name_norm=rec_mod.normalize_name(name)))
        if status == "restricted" and r["status"] != "restricted":
            from ...db import tombstone
            tombstone(conn, "instrument", number)
        audit(conn, user["email"], "instrument.edit", "instrument", number,
              {"status": status, "reason": str(form.get("reason", ""))})
    flash(request, "Index information saved. The official record images were not changed.")
    return RedirectResponse(f"/staff/records/{number}", status_code=303)


def _image(conn, number: str, seq: int):
    r = rec_mod.get(conn, number, include_restricted=True)
    if r is None:
        raise HTTPException(404)
    match = [i for i in r["images"] if i["seq"] == seq]
    if not match:
        raise HTTPException(404)
    return r, match[0]


@router.get("/{number}/pages/{seq}/original.png")
def original_page(request: Request, number: str, seq: int):
    with get_engine().connect() as conn:
        auth.require(request, conn, "records")
        _, image = _image(conn, number, seq)
    data = img.render_page(get_settings().images_dir / image["path"], image["frame"], [])
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{number}/pages/{seq}/redact")
def redact_page(request: Request, number: str, seq: int, scan: int = 0):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "records")
        r, image = _image(conn, number, seq)
        marks = rec_mod.marks_for(conn, image["id"])
        suggestions = img.find_sensitive(get_settings().images_dir / image["path"], image["frame"]) if scan else []
        requests_open = conn.execute(select(redaction_requests).where(
            redaction_requests.c.status.in_(["received", "approved"]))).mappings().all()
        return staff_render(request, "staff/redact.html", conn, user, page_title=f"Redact {number} page {seq}", r=r,
                            image=image, marks=marks, suggestions=suggestions, scanned=bool(scan),
                            requests_open=requests_open, ocr=img.ocr_available())


@router.post("/{number}/pages/{seq}/marks", dependencies=[Depends(verify_csrf)])
async def add_mark(request: Request, number: str, seq: int):
    form = await request.form()
    try:
        vals = [float(str(form.get(k, "")).strip()) for k in ("x", "y", "w", "h")]
    except ValueError:
        flash(request, "Enter all four box numbers as percentages, like 12.5.", "error")
        return RedirectResponse(f"/staff/records/{number}/pages/{seq}/redact", status_code=303)
    reason = str(form.get("reason", "")).strip()
    if not reason:
        flash(request, "Give the reason for the redaction (for example: SSN, Property Code 11.008).", "error")
        return RedirectResponse(f"/staff/records/{number}/pages/{seq}/redact", status_code=303)
    scale = 1 if form.get("units") == "permille" else 10
    x, y, w, h = (max(0, min(1000, round(v * scale))) for v in vals)
    if w <= 0 or h <= 0:
        flash(request, "The box needs a width and height greater than zero.", "error")
        return RedirectResponse(f"/staff/records/{number}/pages/{seq}/redact", status_code=303)
    with tx() as conn:
        user = auth.require(request, conn, "records")
        _, image = _image(conn, number, seq)
        req_id = int(form.get("request_id") or 0) or None
        conn.execute(redaction_marks.insert().values(image_id=image["id"], request_id=req_id, x=x, y=y, w=w, h=h,
                                                     reason=reason, created_by=user["email"]))
        _refresh_flags(conn, [image["id"]])
        audit(conn, user["email"], "redaction.mark", "instrument", number, {"seq": seq, "box": [x, y, w, h], "reason": reason})
    flash(request, "Redaction added. The public copy of this page now hides that area; the original is unchanged.")
    return RedirectResponse(f"/staff/records/{number}/pages/{seq}/redact", status_code=303)


@router.post("/{number}/pages/{seq}/marks/{mark_id}/delete", dependencies=[Depends(verify_csrf)])
async def delete_mark(request: Request, number: str, seq: int, mark_id: int):
    with tx() as conn:
        user = auth.require(request, conn, "records")
        _, image = _image(conn, number, seq)
        conn.execute(redaction_marks.delete().where(redaction_marks.c.id == mark_id,
                                                    redaction_marks.c.image_id == image["id"]))
        _refresh_flags(conn, [image["id"]])
        audit(conn, user["email"], "redaction.unmark", "instrument", number, {"seq": seq, "mark": mark_id})
    flash(request, "Redaction removed.")
    return RedirectResponse(f"/staff/records/{number}/pages/{seq}/redact", status_code=303)


@router.post("/{number}/ocr", dependencies=[Depends(verify_csrf)])
async def rerun_ocr(request: Request, number: str):
    with tx() as conn:
        user = auth.require(request, conn, "records")
        r = rec_mod.get(conn, number, include_restricted=True)
        if r is None:
            raise HTTPException(404)
        for i in r["images"]:
            text = img.ocr(get_settings().images_dir / i["path"], i["frame"])
            conn.execute(images.update().where(images.c.id == i["id"]).values(ocr_text=text, public_text=None,
                                                                             updated_at=utcnow()))
        audit(conn, user["email"], "instrument.ocr", "instrument", number)
    flash(request, "Text re-read from every page.")
    return RedirectResponse(f"/staff/records/{number}", status_code=303)
