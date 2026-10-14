"""The free, open API. Read-only, no key required, the same data the website
shows. Also serves the bulk files and the Data.gov catalogs."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import __version__, config_store, fees as fee_mod, records as rec_mod
from ..db import (get_engine, instruments, meetings, offices, pages, pia_requests, postings, services, tombstones,
                  fees as fees_table)
from ..settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["Open data"])


class Image(BaseModel):
    seq: int
    url: str
    sha256: str
    text: Optional[str] = None


class Instrument(BaseModel):
    instrument_number: str
    doc_type: str
    recorded_date: Optional[dt.date] = None
    book: Optional[str] = None
    page: Optional[str] = None
    grantors: list[str]
    grantees: list[str]
    legal_description: Optional[str] = None
    property_id: Optional[str] = None
    page_count: int
    remarks: Optional[str] = None
    updated_at: dt.datetime
    url: str
    pdf_url: str
    images: Optional[list[Image]] = None


class Page(BaseModel):
    data: list
    total: Optional[int] = None
    next: Optional[str] = None


def _instrument(r: dict, base: str, with_images: bool = False) -> dict:
    out = {k: r.get(k) for k in ("instrument_number", "doc_type", "recorded_date", "book", "page",
                                 "legal_description", "property_id", "page_count", "remarks", "updated_at")}
    out["grantors"] = r.get("grantors", [])
    out["grantees"] = r.get("grantees", [])
    out["url"] = f"{base}/records/{r['instrument_number']}"
    out["pdf_url"] = f"{base}/records/{r['instrument_number']}/download.pdf"
    if with_images:
        out["images"] = [{"seq": i["seq"], "url": f"{base}/records/{r['instrument_number']}/pages/{i['seq']}.png",
                          "sha256": i["sha256"], "text": rec_mod.public_text(i)} for i in r.get("images", [])]
    return out


@router.get("", summary="API index")
def index() -> dict:
    base = get_settings().site_url
    return {"name": "Open County Portal API", "version": __version__, "documentation": f"{base}/data",
            "openapi": f"{base}/api/v1/openapi.json", "catalog": f"{base}/data.json",
            "endpoints": {k: f"{base}/api/v1/{k}" for k in ("instruments", "meetings", "postings", "fees", "services",
                                                           "offices", "pages", "public-information", "changes", "bulk")},
            "terms": "Free. No key required. Please use the bulk files for large downloads."}


@router.get("/instruments", response_model=Page, summary="Search recorded instruments")
def list_instruments(name: str = "", role: str = Query("any", pattern="^(any|grantor|grantee)$"), doc_type: str = "",
                     recorded_from: Optional[dt.date] = None, recorded_to: Optional[dt.date] = None,
                     property_id: str = "", updated_since: Optional[dt.datetime] = None,
                     limit: int = Query(50, ge=1, le=200), page: int = Query(1, ge=1)):
    q = rec_mod.Query(name=name, role=role, doc_type=doc_type, date_from=recorded_from, date_to=recorded_to,
                      property_id=property_id, updated_since=updated_since)
    base = get_settings().site_url
    with get_engine().connect() as conn:
        if q.is_empty():
            q.updated_since = dt.datetime(1900, 1, 1, tzinfo=dt.timezone.utc)
        rows, total = rec_mod.search(conn, q, page=page, page_size=limit)
    nxt = None
    if page * limit < total:
        params = {k: v for k, v in {"name": name, "role": role, "doc_type": doc_type, "recorded_from": recorded_from,
                                     "recorded_to": recorded_to, "property_id": property_id,
                                     "updated_since": updated_since, "limit": limit, "page": page + 1}.items() if v}
        nxt = f"{base}/api/v1/instruments?" + "&".join(f"{k}={v}" for k, v in params.items())
    return {"data": [_instrument(r, base) for r in rows], "total": total, "next": nxt}


@router.get("/instruments/{number}", response_model=Instrument, summary="One recorded instrument with page images")
def get_instrument(number: str):
    with get_engine().connect() as conn:
        r = rec_mod.get(conn, number)
    if r is None:
        raise HTTPException(404, "No public instrument with that number.")
    return _instrument(r, get_settings().site_url, with_images=True)


def _rows(conn, stmt) -> list[dict]:
    return [dict(r) for r in conn.execute(stmt).mappings()]


@router.get("/meetings", response_model=Page, summary="Meetings, agendas and minutes")
def list_meetings(updated_since: Optional[dt.datetime] = None, limit: int = Query(100, ge=1, le=500)):
    stmt = select(meetings).where(meetings.c.status.in_(["posted", "held", "cancelled"]))
    if updated_since:
        stmt = stmt.where(meetings.c.updated_at >= updated_since)
    with get_engine().connect() as conn:
        data = _rows(conn, stmt.order_by(meetings.c.starts_at.desc()).limit(limit))
    return {"data": data}


@router.get("/postings", response_model=Page, summary="Public notices and required postings")
def list_postings(updated_since: Optional[dt.datetime] = None):
    stmt = select(postings).where(postings.c.published.is_(True))
    if updated_since:
        stmt = stmt.where(postings.c.updated_at >= updated_since)
    with get_engine().connect() as conn:
        data = _rows(conn, stmt.order_by(postings.c.posted_at.desc()))
    return {"data": data}


@router.get("/fees", response_model=Page, summary="Current and scheduled fees")
def list_fees():
    with get_engine().connect() as conn:
        data = fee_mod.all_current(conn) + fee_mod.scheduled(conn)
    for f in data:
        f["amount"] = f"{f['amount_cents'] / 100:.2f}"
    return {"data": data}


@router.get("/services", response_model=Page, summary="Services directory")
def list_services():
    with get_engine().connect() as conn:
        return {"data": _rows(conn, select(services).where(services.c.published.is_(True)).order_by(services.c.sort))}


@router.get("/offices", response_model=Page, summary="Offices, hours and contacts")
def list_offices():
    cols = [c for c in offices.c if c.name != "merchant_account"]
    with get_engine().connect() as conn:
        return {"data": _rows(conn, select(*cols).where(offices.c.active.is_(True)).order_by(offices.c.sort))}


@router.get("/pages", response_model=Page, summary="Published information pages (Markdown)")
def list_pages():
    with get_engine().connect() as conn:
        return {"data": _rows(conn, select(pages.c.slug, pages.c.title, pages.c.body, pages.c.updated_at)
                              .where(pages.c.published.is_(True)).order_by(pages.c.slug))}


@router.get("/public-information", response_model=Page, summary="Released public information responses")
def list_pia():
    with get_engine().connect() as conn:
        return {"data": _rows(conn, select(pia_requests.c.number, pia_requests.c.description, pia_requests.c.response,
                                           pia_requests.c.received_at, pia_requests.c.status, pia_requests.c.updated_at)
                              .where(pia_requests.c.publish_response.is_(True))
                              .order_by(pia_requests.c.received_at.desc()))}


@router.get("/changes", response_model=Page, summary="Everything created, changed or removed since a time")
def changes(since: dt.datetime, limit: int = Query(1000, ge=1, le=5000)):
    base = get_settings().site_url
    out: list[dict] = []
    with get_engine().connect() as conn:
        for r in conn.execute(select(instruments.c.instrument_number, instruments.c.updated_at)
                              .where(instruments.c.updated_at >= since, instruments.c.status == "public")
                              .order_by(instruments.c.updated_at).limit(limit)):
            out.append({"type": "instrument", "id": r.instrument_number, "change": "upsert", "at": r.updated_at,
                        "url": f"{base}/api/v1/instruments/{r.instrument_number}"})
        for table, kind, key in ((meetings, "meeting", "id"), (postings, "posting", "id"), (services, "service", "slug"),
                                 (offices, "office", "slug"), (fees_table, "fee", "code")):
            for r in conn.execute(select(table.c[key], table.c.updated_at).where(table.c.updated_at >= since)
                                  .order_by(table.c.updated_at).limit(limit)):
                out.append({"type": kind, "id": str(r[0]), "change": "upsert", "at": r.updated_at})
        for r in conn.execute(select(tombstones).where(tombstones.c.deleted_at >= since)
                              .order_by(tombstones.c.deleted_at).limit(limit)).mappings():
            out.append({"type": r["object_type"], "id": r["object_id"], "change": "delete", "at": r["deleted_at"]})
    out.sort(key=lambda c: c["at"])
    return {"data": out[:limit]}


@router.get("/bulk", summary="Daily bulk files with checksums")
def bulk_index():
    latest = get_settings().bulk_dir / "latest" / "manifest.json"
    if not latest.exists():
        return {"files": [], "message": "Bulk files have not been generated yet. They are created nightly."}
    return json.loads(latest.read_text(encoding="utf-8"))


@router.get("/bulk/{name}", summary="Download one bulk file", response_class=FileResponse)
def bulk_file(name: str):
    if "/" in name or name.startswith("."):
        raise HTTPException(404)
    path = get_settings().bulk_dir / "latest" / name
    if not path.exists():
        raise HTTPException(404, "No bulk file with that name.")
    media = "text/csv" if name.endswith(".csv") else "application/jsonl" if name.endswith(".jsonl") else "application/json"
    return FileResponse(path, media_type=media, filename=name)


# ---- Data.gov catalogs ------------------------------------------------------------

DATASETS = [
    ("records", "Real property records index", "Index of recorded real property instruments (deeds, liens, plats, "
     "releases) with grantors, grantees, legal descriptions and links to page images.",
     ["real property", "deeds", "land records", "county clerk"], instruments, "instruments"),
    ("meetings", "Meetings and agendas", "Notices, agendas and minutes of public meetings.",
     ["meetings", "agendas", "minutes", "open meetings"], meetings, "meetings"),
    ("postings", "Public notices", "Notices and postings required by state law.",
     ["public notices", "transparency"], postings, "postings"),
    ("fees", "Fee schedule", "Current and scheduled fees, with the statute or order that sets each fee.",
     ["fees", "fee schedule"], fees_table, "fees"),
    ("services", "Services directory", "Services offered to residents, with who can apply and what is needed.",
     ["services", "government services"], services, "services"),
]


def _modified(conn, table) -> str:
    v = conn.execute(select(func.max(table.c.updated_at))).scalar()
    return (v or dt.datetime.now(dt.timezone.utc)).date().isoformat()


def _catalog_parts():
    base = get_settings().site_url
    with get_engine().connect() as conn:
        site = config_store.get(conn, "site")
        od = config_store.get(conn, "open_data")
        mods = {slug: _modified(conn, table) for slug, *_rest, table, _api in DATASETS}
    email = od.get("contact_email") or site.get("email") or ""
    return base, site, od, mods, email


catalog_router = APIRouter(tags=["Data catalog"])


@catalog_router.get("/data.json", summary="Data catalog (DCAT-US 3.0) for Data.gov harvesting")
def data_json():
    base, site, od, mods, email = _catalog_parts()
    datasets = []
    for slug, title, desc, keywords, _table, api in DATASETS:
        ds = {
            "@type": "Dataset",
            "title": f"{site['jurisdiction_name']}: {title}",
            "description": desc,
            "identifier": f"{base}/data#{slug}",
            "contactPoint": {"fn": od.get("contact_name") or site["jurisdiction_name"], "hasEmail": f"mailto:{email}"},
            "publisher": {"@type": "Organization", "name": site["jurisdiction_name"]},
            "keyword": keywords + [site.get("state_name") or ""],
            "modified": mods[slug],
            "accessRights": "public",
            "accrualPeriodicity": "daily",
            "distribution": [
                {"title": f"{title} (API, JSON)", "accessURL": f"{base}/api/v1/{api}", "mediaType": "application/json",
                 "format": "API"},
            ],
        }
        if slug == "records":
            ds["distribution"] += [
                {"title": "Instruments (CSV, daily)", "downloadURL": f"{base}/api/v1/bulk/instruments.csv",
                 "mediaType": "text/csv", "format": "CSV"},
                {"title": "Instruments (JSON Lines, daily)", "downloadURL": f"{base}/api/v1/bulk/instruments.jsonl",
                 "mediaType": "application/jsonl", "format": "JSON Lines"}]
        else:
            ds["distribution"].append({"title": f"{title} (JSON, daily)", "downloadURL": f"{base}/api/v1/bulk/{api}.json",
                                       "mediaType": "application/json", "format": "JSON"})
        if od.get("license_url"):
            ds["license"] = od["license_url"]
            for dist in ds["distribution"]:  # DCAT-US 3.0 recommends the license on each distribution
                dist["license"] = od["license_url"]
        ds["keyword"] = [k for k in ds["keyword"] if k]
        datasets.append(ds)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalog = {"@type": "Catalog",
               "conformsTo": {"@type": "Standard", "title": "DCAT-US 3.0",
                              "identifier": "https://resources.data.gov/dcat-us/3.0.0"},
               "title": f"{site['jurisdiction_name']} open data",
               "description": f"Public data published by {site['jurisdiction_name']}, {site.get('state_name', '')}.",
               "publisher": {"@type": "Organization", "name": site["jurisdiction_name"]}, "language": ["en"],
               "modified": now, "dataset": datasets}
    return JSONResponse(catalog, headers={"Access-Control-Allow-Origin": "*"})


@catalog_router.get("/data-v1.1.json", summary="Data catalog (DCAT-US 1.1 / Project Open Data) for Data.gov harvesting")
def data_json_v11():
    base, site, od, mods, email = _catalog_parts()
    datasets = []
    for slug, title, desc, keywords, _table, api in DATASETS:
        dist = [{"@type": "dcat:Distribution", "title": f"{title} (API, JSON)", "accessURL": f"{base}/api/v1/{api}",
                 "format": "API", "mediaType": "application/json"}]
        if slug == "records":
            dist.append({"@type": "dcat:Distribution", "title": "Instruments (CSV, daily)",
                         "downloadURL": f"{base}/api/v1/bulk/instruments.csv", "mediaType": "text/csv"})
        else:
            dist.append({"@type": "dcat:Distribution", "title": f"{title} (JSON, daily)",
                         "downloadURL": f"{base}/api/v1/bulk/{api}.json", "mediaType": "application/json"})
        ds = {"@type": "dcat:Dataset", "title": f"{site['jurisdiction_name']}: {title}", "description": desc,
              "keyword": [k for k in keywords + [site.get("state_name") or ""] if k], "modified": mods[slug],
              "publisher": {"@type": "org:Organization", "name": site["jurisdiction_name"]},
              "contactPoint": {"@type": "vcard:Contact", "fn": od.get("contact_name") or site["jurisdiction_name"],
                               "hasEmail": f"mailto:{email}"},
              "identifier": f"{base}/data#{slug}", "accessLevel": "public", "accrualPeriodicity": "R/P1D",
              "distribution": dist}
        if od.get("license_url"):
            ds["license"] = od["license_url"]
        datasets.append(ds)
    catalog = {"@context": "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld",
               "@type": "dcat:Catalog", "conformsTo": "https://project-open-data.cio.gov/v1.1/schema",
               "describedBy": "https://project-open-data.cio.gov/v1.1/schema/catalog.json", "dataset": datasets}
    return JSONResponse(catalog, headers={"Access-Control-Allow-Origin": "*"})
