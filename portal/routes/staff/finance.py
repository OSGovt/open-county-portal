"""Finance: totals, general-ledger export, payment posting files, escrow."""
from __future__ import annotations

import csv
import datetime as dt
import io
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select

from ... import auth, config_store
from ...db import (audit, drawer_sessions, drawers, escrow_accounts, escrow_ledger, get_engine, offices, order_lines,
                   orders, tenders, tx)
from ...web import flash, money, parse_money, verify_csrf
from .common import staff_render

router = APIRouter(prefix="/finance")


def _range(conn, start: str, end: str) -> tuple[dt.datetime, dt.datetime, dt.date, dt.date]:
    tz = ZoneInfo(config_store.get(conn, "site").get("timezone") or "America/Chicago")
    today = dt.datetime.now(tz).date()
    try:
        d0 = dt.date.fromisoformat(start) if start else today
        d1 = dt.date.fromisoformat(end) if end else d0
    except ValueError:
        d0 = d1 = today
    if d1 < d0:
        d0, d1 = d1, d0
    t0 = dt.datetime.combine(d0, dt.time.min, tz)
    t1 = dt.datetime.combine(d1 + dt.timedelta(days=1), dt.time.min, tz)
    return t0, t1, d0, d1


def _paid(t0, t1):
    return [orders.c.status == "paid", orders.c.paid_at >= t0, orders.c.paid_at < t1]


@router.get("")
def report(request: Request, start: str = "", end: str = ""):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "finance", "supervisor")
        t0, t1, d0, d1 = _range(conn, start, end)
        names = {r.slug: r.name for r in conn.execute(select(offices.c.slug, offices.c.name))}
        by_fund = conn.execute(select(order_lines.c.office_slug, order_lines.c.fund, func.sum(order_lines.c.amount_cents))
                               .select_from(order_lines.join(orders, orders.c.id == order_lines.c.order_id))
                               .where(*_paid(t0, t1)).group_by(order_lines.c.office_slug, order_lines.c.fund)
                               .order_by(order_lines.c.office_slug, order_lines.c.fund)).all()
        by_tender = conn.execute(select(orders.c.channel, tenders.c.kind, func.count(), func.sum(tenders.c.amount_cents))
                                 .select_from(tenders.join(orders, orders.c.id == tenders.c.order_id))
                                 .where(*_paid(t0, t1)).group_by(orders.c.channel, tenders.c.kind)).all()
        fees_total = conn.execute(select(func.coalesce(func.sum(orders.c.fee_cents), 0)).where(*_paid(t0, t1))).scalar_one()
        voids = conn.execute(select(orders).where(orders.c.status == "void", orders.c.paid_at >= t0,
                                                  orders.c.paid_at < t1)).mappings().all()
        drawer_rows = conn.execute(select(drawer_sessions, drawers.c.name.label("drawer_name"))
                                   .select_from(drawer_sessions.join(drawers, drawers.c.id == drawer_sessions.c.drawer_id))
                                   .where(drawer_sessions.c.opened_at >= t0, drawer_sessions.c.opened_at < t1)
                                   .order_by(drawer_sessions.c.opened_at)).mappings().all()
        escrows = conn.execute(select(escrow_accounts).order_by(escrow_accounts.c.name)).mappings().all()
        return staff_render(request, "staff/finance.html", conn, user, page_title="Finance", d0=d0, d1=d1,
                            by_fund=by_fund, by_tender=by_tender, fees_total=fees_total, voids=voids,
                            drawer_rows=drawer_rows, names=names, escrows=escrows)


def _csv(rows: list[list], header: list[str], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/ledger.csv")
def ledger(request: Request, start: str = "", end: str = ""):
    """One row per order line: what to post to which office and fund."""
    with get_engine().connect() as conn:
        auth.require(request, conn, "finance", "supervisor")
        t0, t1, d0, d1 = _range(conn, start, end)
        rows = conn.execute(select(orders.c.paid_at, orders.c.number, orders.c.channel, order_lines.c.office_slug,
                                   order_lines.c.fund, order_lines.c.fee_code, order_lines.c.statute, order_lines.c.label,
                                   order_lines.c.qty, order_lines.c.amount_cents, order_lines.c.ref)
                            .select_from(order_lines.join(orders, orders.c.id == order_lines.c.order_id))
                            .where(*_paid(t0, t1)).order_by(orders.c.paid_at, order_lines.c.id)).all()
        fee_rows = conn.execute(select(orders.c.paid_at, orders.c.number, orders.c.channel, orders.c.fee_cents)
                                .where(*_paid(t0, t1), orders.c.fee_cents > 0)).all()
    out = [[r.paid_at.isoformat(), r.number, r.channel, r.office_slug, r.fund, r.fee_code or "", r.statute or "",
            r.label, r.qty, f"{r.amount_cents / 100:.2f}", r.ref or ""] for r in rows]
    out += [[r.paid_at.isoformat(), r.number, r.channel, "", "Card processing reimbursement", "", "", "Processing fee", 1,
             f"{r.fee_cents / 100:.2f}", ""] for r in fee_rows]
    return _csv(out, ["paid_at", "order", "channel", "office", "fund", "fee_code", "statute", "description", "qty",
                      "amount", "reference"], f"ledger-{d0}-to-{d1}.csv")


@router.get("/posting.csv")
def posting(request: Request, start: str = "", end: str = "", kind: str = ""):
    """Bill payments to post back into the tax, court or utility system."""
    with get_engine().connect() as conn:
        auth.require(request, conn, "finance", "supervisor")
        t0, t1, d0, d1 = _range(conn, start, end)
        rows = conn.execute(select(orders.c.paid_at, orders.c.number, order_lines.c.office_slug, order_lines.c.ref,
                                   order_lines.c.amount_cents, order_lines.c.label)
                            .select_from(order_lines.join(orders, orders.c.id == order_lines.c.order_id))
                            .where(*_paid(t0, t1), order_lines.c.kind == "receivable")
                            .order_by(orders.c.paid_at)).all()
    return _csv([[r.paid_at.isoformat(), r.number, r.office_slug, r.ref, f"{r.amount_cents / 100:.2f}", r.label]
                 for r in rows], ["paid_at", "order", "office", "account", "amount", "description"],
                f"bill-payments-{d0}-to-{d1}.csv")


@router.post("/escrow", dependencies=[Depends(verify_csrf)])
async def escrow_action(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "finance", "supervisor")
        action = form.get("action")
        if action == "create":
            name = str(form.get("name", "")).strip()
            if not name:
                flash(request, "Enter the account holder's name.", "error")
                return RedirectResponse("/staff/finance", status_code=303)
            conn.execute(escrow_accounts.insert().values(name=name, email=str(form.get("email", "")).strip() or None))
            audit(conn, user["email"], "escrow.create", "escrow", name)
            flash(request, f"Escrow account for {name} created.")
        elif action == "deposit":
            amount = parse_money(str(form.get("amount", "")))
            acct_id = int(form.get("account_id", 0) or 0)
            acct = conn.execute(select(escrow_accounts).where(escrow_accounts.c.id == acct_id)).mappings().first()
            if acct is None or not amount:
                flash(request, "Choose an account and enter the deposit amount.", "error")
                return RedirectResponse("/staff/finance", status_code=303)
            conn.execute(escrow_accounts.update().where(escrow_accounts.c.id == acct_id)
                         .values(balance_cents=acct["balance_cents"] + amount))
            conn.execute(escrow_ledger.insert().values(account_id=acct_id, amount_cents=amount, by_user=user["email"],
                                                       note=str(form.get("note", "Deposit")) or "Deposit"))
            audit(conn, user["email"], "escrow.deposit", "escrow", acct_id, {"amount_cents": amount})
            flash(request, f"Deposited {money(amount)} to {acct['name']}.")
    return RedirectResponse("/staff/finance", status_code=303)
