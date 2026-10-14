"""Meetings, agendas, minutes and required public postings."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select

from .. import config_store, statepacks
from ..db import files, get_engine, meetings, postings, utcnow
from ..web import render

router = APIRouter()


@router.get("/meetings", include_in_schema=False)
def meeting_list(request: Request):
    with get_engine().connect() as conn:
        now = utcnow()
        upcoming = conn.execute(select(meetings).where(meetings.c.status.in_(["posted", "cancelled"]),
                                                       meetings.c.starts_at >= now - dt.timedelta(hours=6))
                                .order_by(meetings.c.starts_at)).mappings().all()
        past = conn.execute(select(meetings).where(meetings.c.status.in_(["posted", "held"]),
                                                   meetings.c.starts_at < now - dt.timedelta(hours=6))
                            .order_by(meetings.c.starts_at.desc()).limit(50)).mappings().all()
        return render(request, "public/meetings.html", conn, page_title="Meetings and agendas", nav="meetings",
                      upcoming=upcoming, past=past)


@router.get("/meetings/{meeting_id}", include_in_schema=False)
def meeting_detail(request: Request, meeting_id: int):
    with get_engine().connect() as conn:
        m = conn.execute(select(meetings).where(meetings.c.id == meeting_id,
                                                meetings.c.status.in_(["posted", "held", "cancelled"]))).mappings().first()
        if m is None:
            raise HTTPException(404)
        return render(request, "public/meeting.html", conn, page_title=f"{m['title']}", nav="meetings", m=m)


@router.get("/notices", include_in_schema=False)
def notices(request: Request):
    with get_engine().connect() as conn:
        today = dt.date.today()
        rows = conn.execute(select(postings, files.c.name.label("file_name"))
                            .select_from(postings.outerjoin(files, files.c.id == postings.c.file_id))
                            .where(postings.c.published.is_(True),
                                   or_(postings.c.remove_after.is_(None), postings.c.remove_after >= today))
                            .order_by(postings.c.posted_at.desc())).mappings().all()
        site = config_store.get(conn, "site")
        try:
            rules = {r["code"]: r for r in statepacks.posting_rules(site["state"], site["jurisdiction_type"])}
        except statepacks.PackError:
            rules = {}
        return render(request, "public/notices.html", conn, page_title="Public notices", rows=rows, rules=rules)
