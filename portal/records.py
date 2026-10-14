"""Records search and retrieval, shared by the website and the open API."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.engine import Connection

from .db import images, instruments, parties, redaction_marks

PAGE_SIZE = 25


def normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s&'-]", " ", (name or "").upper())
    return re.sub(r"\s+", " ", cleaned).strip()


@dataclass
class Query:
    name: str = ""
    role: str = "any"  # any | grantor | grantee
    doc_type: str = ""
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    instrument_number: str = ""
    book: str = ""
    page: str = ""
    legal: str = ""
    property_id: str = ""
    updated_since: dt.datetime | None = None

    def is_empty(self) -> bool:
        return not any([self.name.strip(), self.doc_type, self.date_from, self.date_to,
                        self.instrument_number.strip(), self.book.strip(), self.legal.strip(),
                        self.property_id.strip(), self.updated_since])


def build(q: Query):
    cond = [instruments.c.status == "public"]
    if q.name.strip():
        norm = normalize_name(q.name)
        pcond = [parties.c.instrument_id == instruments.c.id, parties.c.name_norm.like(f"%{norm}%")]
        if q.role in ("grantor", "grantee"):
            pcond.append(parties.c.role == q.role)
        cond.append(exists(select(parties.c.id).where(and_(*pcond))))
    if q.doc_type:
        cond.append(instruments.c.doc_type == q.doc_type)
    if q.date_from:
        cond.append(instruments.c.recorded_date >= q.date_from)
    if q.date_to:
        cond.append(instruments.c.recorded_date <= q.date_to)
    if q.instrument_number.strip():
        cond.append(instruments.c.instrument_number.ilike(f"{q.instrument_number.strip()}%"))
    if q.book.strip():
        cond.append(instruments.c.book == q.book.strip())
    if q.page.strip():
        cond.append(instruments.c.page == q.page.strip())
    if q.legal.strip():
        cond.append(instruments.c.legal_description.ilike(f"%{q.legal.strip()}%"))
    if q.property_id.strip():
        cond.append(instruments.c.property_id == q.property_id.strip())
    if q.updated_since:
        cond.append(instruments.c.updated_at >= q.updated_since)
    return and_(*cond)


def search(conn: Connection, q: Query, page: int = 1, page_size: int = PAGE_SIZE) -> tuple[list[dict], int]:
    where = build(q)
    total = conn.execute(select(func.count()).select_from(instruments).where(where)).scalar_one()
    rows = conn.execute(select(instruments).where(where)
                        .order_by(instruments.c.recorded_date.desc().nulls_last(), instruments.c.instrument_number.desc())
                        .limit(page_size).offset(max(0, page - 1) * page_size)).mappings().all()
    out = [dict(r) for r in rows]
    attach_parties(conn, out)
    return out, total


def attach_parties(conn: Connection, rows: list[dict]) -> None:
    ids = [r["id"] for r in rows]
    if not ids:
        return
    by: dict[int, dict[str, list[str]]] = {i: {"grantor": [], "grantee": []} for i in ids}
    for p in conn.execute(select(parties).where(parties.c.instrument_id.in_(ids)).order_by(parties.c.id)).mappings():
        by[p["instrument_id"]].setdefault(p["role"], []).append(p["name"])
    for r in rows:
        r["grantors"] = by[r["id"]].get("grantor", [])
        r["grantees"] = by[r["id"]].get("grantee", [])


def get(conn: Connection, number: str, include_restricted: bool = False) -> dict | None:
    cond = [instruments.c.instrument_number == number]
    if not include_restricted:
        cond.append(instruments.c.status == "public")
    row = conn.execute(select(instruments).where(*cond)).mappings().first()
    if row is None:
        return None
    rec = dict(row)
    attach_parties(conn, [rec])
    rec["images"] = [dict(i) for i in conn.execute(select(images).where(images.c.instrument_id == rec["id"])
                                                   .order_by(images.c.seq)).mappings()]
    return rec


def marks_for(conn: Connection, image_id: int) -> list[dict]:
    return [dict(m) for m in conn.execute(select(redaction_marks).where(redaction_marks.c.image_id == image_id)).mappings()]


def doc_types(conn: Connection) -> list[str]:
    return [r for r in conn.execute(select(instruments.c.doc_type).where(instruments.c.status == "public")
                                    .distinct().order_by(instruments.c.doc_type)).scalars()]


def parse_date(text: str | None) -> dt.date | None:
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text.strip())
    except ValueError:
        return None
