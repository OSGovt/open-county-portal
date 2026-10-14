"""Staff dashboard: what needs attention today."""
from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from ... import auth, compliance, ops_status
from ...db import applications, get_engine, import_batches, order_lines, orders, pia_requests, redaction_requests
from .common import staff_render

router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn)
        count = lambda stmt: conn.execute(stmt).scalar_one()  # noqa: E731
        queues = [
            ("Certified copies to prepare", "/staff/orders", ("records",),
             count(select(func.count()).select_from(order_lines.join(orders, orders.c.id == order_lines.c.order_id))
                   .where(order_lines.c.fulfil_status == "pending", orders.c.status == "paid"))),
            ("Public information requests open", "/staff/pia", ("pia",),
             count(select(func.count()).select_from(pia_requests).where(pia_requests.c.status.notin_(["closed", "released"])))),
            ("Applications to review", "/staff/applications", ("applications",),
             count(select(func.count()).select_from(applications).where(applications.c.status == "received"))),
            ("Redaction requests to decide", "/staff/records/redactions", ("records",),
             count(select(func.count()).select_from(redaction_requests).where(redaction_requests.c.status == "received"))),
            ("Online orders awaiting payment at the office", "/staff/counter/orders", ("cashier",),
             count(select(func.count()).select_from(orders).where(orders.c.status == "pending", orders.c.processor == "manual"))),
            ("Imports waiting for sign-off", "/staff/system/migrations", ("admin",),
             count(select(func.count()).select_from(import_batches).where(import_batches.c.status == "loaded"))),
        ]
        queues = [q for q in queues if auth.has_role(user, *q[2])]
        postings = compliance.check_postings(conn) if auth.has_role(user, "admin", "content") else []
        status = ops_status.summary() if auth.has_role(user, "admin") else None
        return staff_render(request, "staff/dashboard.html", conn, user, page_title="Staff dashboard", queues=queues,
                            postings=postings, status=status)
