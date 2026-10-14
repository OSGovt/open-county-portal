"""Public records: search, record pages, page images, free PDF downloads,
accessible-version requests and protected-person redaction requests."""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from .. import config_store, images as img, records as rec_mod, statepacks
from ..db import applications, audit, next_number, redaction_requests, tx
from ..db import get_engine
from ..web import client_ip, flash, render, verify_csrf

router = APIRouter()


def _pack(conn):
    site = config_store.get(conn, "site")
    try:
        return statepacks.load(site["state"])
    except statepacks.PackError:
        return {"records": {}}


@router.get("/records", include_in_schema=False)
def search_page(request: Request, name: str = "", role: str = "any", doc_type: str = "", date_from: str = "",
                date_to: str = "", instrument_number: str = "", book: str = "", page_ref: str = "",
                legal: str = "", page: int = 1):
    q = rec_mod.Query(name=name, role=role, doc_type=doc_type, date_from=rec_mod.parse_date(date_from),
                      date_to=rec_mod.parse_date(date_to), instrument_number=instrument_number, book=book,
                      page=page_ref, legal=legal)
    errors = {}
    if date_from and not q.date_from:
        errors["date_from"] = "Enter the start date as a date, like 2024-01-31."
    if date_to and not q.date_to:
        errors["date_to"] = "Enter the end date as a date, like 2024-12-31."
    searched = any(request.query_params.get(k) for k in ("name", "doc_type", "date_from", "date_to",
                                                          "instrument_number", "book", "page_ref", "legal"))
    with get_engine().connect() as conn:
        results, total = ([], 0)
        if searched and not errors:
            if q.is_empty():
                errors["name"] = "Enter a name, an instrument number, or another search detail."
            else:
                results, total = rec_mod.search(conn, q, page=max(1, page))
        pages = max(1, math.ceil(total / rec_mod.PAGE_SIZE))
        query_string = "&".join(f"{k}={v}" for k, v in request.query_params.items() if k != "page" and v)
        return render(request, "public/records_search.html", conn, page_title="Search property records", nav="records",
                      q=q, results=results, total=total, page=page, pages=pages, searched=searched, errors=errors,
                      doc_types=rec_mod.doc_types(conn), notice=_pack(conn).get("records", {}).get("online_notice"),
                      query_string=query_string, raw={"date_from": date_from, "date_to": date_to, "page_ref": page_ref})


@router.get("/records/redaction-request", include_in_schema=False)
def redaction_form(request: Request):
    with get_engine().connect() as conn:
        return render(request, "public/redaction_request.html", conn, page_title="Ask to remove personal information from online records",
                      nav="records", rules=_pack(conn).get("records", {}).get("redaction", {}), errors={}, values={})


@router.post("/records/redaction-request", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def redaction_submit(request: Request):
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in ("requester_name", "category", "email", "phone", "search_names", "details")}
    errors = {}
    if not values["requester_name"]:
        errors["requester_name"] = "Enter your full name."
    if not values["category"]:
        errors["category"] = "Choose which group you belong to."
    if not values["email"] and not values["phone"]:
        errors["email"] = "Give an email address or phone number so the clerk can reach you."
    if not values["search_names"]:
        errors["search_names"] = "List the names that appear on your property records."
    with tx() as conn:
        if errors:
            return render(request, "public/redaction_request.html", conn, status_code=400,
                          page_title="Ask to remove personal information from online records", nav="records",
                          rules=_pack(conn).get("records", {}).get("redaction", {}), errors=errors, values=values)
        number = next_number(conn, "redaction", "RR")
        conn.execute(redaction_requests.insert().values(number=number, **values))
        audit(conn, None, "redaction.request", "redaction_request", number, ip=client_ip(request))
    flash(request, f"Request {number} received. The County Clerk will verify your eligibility and contact you. "
                   "You will also need to submit the state's signed form if you have not already.")
    return RedirectResponse("/records", status_code=303)


@router.get("/records/{number}", include_in_schema=False)
def record_page(request: Request, number: str, p: int = 1):
    with get_engine().connect() as conn:
        rec = rec_mod.get(conn, number)
        if rec is None:
            raise HTTPException(404)
        count = len(rec["images"])
        p = min(max(1, p), max(1, count))
        current = rec["images"][p - 1] if count else None
        rconf = config_store.get(conn, "records")
        return render(request, "public/record.html", conn, page_title=f"{rec['doc_type']} {rec['instrument_number']}",
                      nav="records", r=rec, p=p, count=count, current=current, rconf=rconf,
                      notice=_pack(conn).get("records", {}).get("online_notice"))


@router.get("/records/{number}/pages/{seq}.png", include_in_schema=False)
def page_image(number: str, seq: int):
    with get_engine().connect() as conn:
        rec = rec_mod.get(conn, number)
        if rec is None:
            raise HTTPException(404)
        match = [i for i in rec["images"] if i["seq"] == seq]
        if not match:
            raise HTTPException(404)
        data = img.cached_page(match[0], rec_mod.marks_for(conn, match[0]["id"]))
    return Response(data, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/records/{number}/download.pdf", include_in_schema=False)
def download_pdf(number: str):
    with get_engine().connect() as conn:
        if not config_store.get(conn, "records").get("free_downloads", True):
            raise HTTPException(403, "Downloads of this document require a copy fee. Use the certified copy option.")
        rec = rec_mod.get(conn, number)
        if rec is None:
            raise HTTPException(404)
        pngs = [img.cached_page(i, rec_mod.marks_for(conn, i["id"])) for i in rec["images"]]
        notice = _pack(conn).get("records", {}).get("online_notice") or ""
    cover = [f"{rec['doc_type']} {rec['instrument_number']}", "Unofficial copy downloaded from the online records database.",
             "Not a certified copy."]
    if notice:
        words, line, lines = notice.split(), "", []
        for w in words:
            if len(line) + len(w) > 70:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        lines.append(line)
        cover += [""] + lines
    data = img.assemble_pdf(pngs, cover)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{number}.pdf"'})


@router.post("/records/{number}/accessible-version", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def accessible_version(request: Request, number: str):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    with tx() as conn:
        rec = rec_mod.get(conn, number)
        if rec is None:
            raise HTTPException(404)
        if "@" not in email:
            flash(request, "Enter your email address so the clerk can send the accessible version.", "error")
            return RedirectResponse(f"/records/{number}#accessible", status_code=303)
        app_no = next_number(conn, "application", "AP")
        conn.execute(applications.insert().values(number=app_no, form="accessible-version", office_slug="county-clerk",
                                                  data={"instrument_number": number, "needs": str(form.get("needs", ""))},
                                                  email=email))
        audit(conn, None, "records.accessible_request", "instrument", number, ip=client_ip(request))
    flash(request, f"Request {app_no} sent. The County Clerk will email an accessible version of {number}.")
    return RedirectResponse(f"/records/{number}", status_code=303)
