"""Orders, payments, receipts, voids and refunds.

An order is created 'pending' from a priced cart, then marked 'paid' when the
processor (or the cashier) confirms payment. Marking paid is idempotent: the
same confirmation arriving twice changes nothing the second time.
"""
from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.engine import Connection

from .cart import Priced
from .db import (applications, audit, escrow_accounts, escrow_ledger, next_number, order_lines, orders,
                 receivables, tenders, utcnow)


def create(conn: Connection, priced: Priced, *, channel: str, method: str, fee_cents: int, email: str | None = None,
           reference: str | None = None, processor: str | None = None, staff_user: str | None = None,
           drawer_session_id: int | None = None) -> dict:
    if not priced.lines:
        raise ValueError("There is nothing to pay for.")
    number = next_number(conn, "order", "PX" if channel == "online" else "CC")
    subtotal = priced.subtotal
    oid = conn.execute(orders.insert().values(
        number=number, token=secrets.token_urlsafe(24), channel=channel, status="pending", email=email,
        reference=reference, subtotal_cents=subtotal, fee_cents=fee_cents, total_cents=subtotal + fee_cents,
        method=method, processor=processor, staff_user=staff_user, drawer_session_id=drawer_session_id)
        .returning(orders.c.id)).scalar_one()
    for l in priced.lines:
        conn.execute(order_lines.insert().values(
            order_id=oid, office_slug=l.office_slug, kind=l.kind, fee_code=l.fee_code, label=l.label, qty=l.qty,
            unit_cents=l.unit_cents, amount_cents=l.amount_cents, statute=l.statute, fund=l.fund, ref=l.ref,
            fulfil_status="pending" if l.fulfil else "none"))
    audit(conn, staff_user, "order.create", "order", number, {"channel": channel, "total_cents": subtotal + fee_cents})
    return get(conn, number)


def get(conn: Connection, number: str) -> dict | None:
    row = conn.execute(select(orders).where(orders.c.number == number)).mappings().first()
    if row is None:
        return None
    o = dict(row)
    o["lines"] = [dict(l) for l in conn.execute(select(order_lines).where(order_lines.c.order_id == o["id"])
                                                .order_by(order_lines.c.id)).mappings()]
    o["tenders"] = [dict(t) for t in conn.execute(select(tenders).where(tenders.c.order_id == o["id"])
                                                  .order_by(tenders.c.id)).mappings()]
    return o


def by_office(order: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for l in order["lines"]:
        out[l["office_slug"]] = out.get(l["office_slug"], 0) + l["amount_cents"]
    return out


def mark_paid(conn: Connection, number: str, tender_list: list[dict], processor_ref: str | None = None,
              actor: str | None = None) -> dict:
    o = conn.execute(select(orders).where(orders.c.number == number).with_for_update()).mappings().first()
    if o is None:
        raise KeyError(number)
    if o["status"] == "paid":
        return get(conn, number)  # already done; confirmation arrived twice
    if o["status"] not in ("pending",):
        raise ValueError(f"Order {number} is {o['status']} and can't be paid.")
    total_tendered = sum(int(t["amount_cents"]) for t in tender_list)
    if total_tendered < o["total_cents"]:
        raise ValueError("The payment is less than the total due.")
    for t in tender_list:
        if t["kind"] == "escrow":
            acct = conn.execute(select(escrow_accounts).where(escrow_accounts.c.id == int(t["account_id"]))
                                .with_for_update()).mappings().first()
            if acct is None or not acct["active"]:
                raise ValueError("That escrow account isn't available.")
            if acct["balance_cents"] < int(t["amount_cents"]):
                raise ValueError(f"The escrow account {acct['name']} doesn't have enough balance.")
            conn.execute(escrow_accounts.update().where(escrow_accounts.c.id == acct["id"])
                         .values(balance_cents=acct["balance_cents"] - int(t["amount_cents"])))
            conn.execute(escrow_ledger.insert().values(account_id=acct["id"], amount_cents=-int(t["amount_cents"]),
                                                       order_id=o["id"], note=f"Order {number}", by_user=actor))
            t = {**t, "detail": f"Escrow: {acct['name']}"}
        conn.execute(tenders.insert().values(order_id=o["id"], kind=t["kind"], amount_cents=int(t["amount_cents"]),
                                             detail=t.get("detail")))
    conn.execute(orders.update().where(orders.c.id == o["id"]).values(status="paid", paid_at=utcnow(),
                                                                       processor_ref=processor_ref))
    lines = conn.execute(select(order_lines).where(order_lines.c.order_id == o["id"])).mappings().all()
    for l in lines:
        if l["kind"] == "receivable":
            r = conn.execute(select(receivables).where(receivables.c.account == l["ref"],
                                                       receivables.c.office_slug == l["office_slug"])
                             .with_for_update()).mappings().first()
            if r is not None:
                conn.execute(receivables.update().where(receivables.c.id == r["id"])
                             .values(amount_due_cents=max(0, r["amount_due_cents"] - l["amount_cents"])))
        if l["kind"] == "application":
            conn.execute(applications.update().where(applications.c.number == l["ref"])
                         .values(status="received", order_id=o["id"]))
    audit(conn, actor, "order.paid", "order", number, {"tenders": [t["kind"] for t in tender_list],
                                                        "processor_ref": processor_ref})
    return get(conn, number)


def mark_failed(conn: Connection, number: str, message: str) -> None:
    conn.execute(orders.update().where(orders.c.number == number, orders.c.status == "pending").values(status="failed"))
    audit(conn, None, "order.failed", "order", number, {"message": message})


def void(conn: Connection, number: str, actor: str, reason: str) -> dict:
    """Cancel a paid order on the same day, reversing receivable and escrow effects."""
    o = get(conn, number)
    if o is None:
        raise KeyError(number)
    if o["status"] != "paid":
        raise ValueError(f"Only paid orders can be voided; this one is {o['status']}.")
    for l in o["lines"]:
        if l["kind"] == "receivable":
            r = conn.execute(select(receivables).where(receivables.c.account == l["ref"],
                                                       receivables.c.office_slug == l["office_slug"])).mappings().first()
            if r is not None:
                conn.execute(receivables.update().where(receivables.c.id == r["id"])
                             .values(amount_due_cents=r["amount_due_cents"] + l["amount_cents"]))
    for t in o["tenders"]:
        if t["kind"] == "escrow":
            entry = conn.execute(select(escrow_ledger).where(escrow_ledger.c.order_id == o["id"])).mappings().first()
            if entry:
                acct = conn.execute(select(escrow_accounts).where(escrow_accounts.c.id == entry["account_id"])).mappings().first()
                conn.execute(escrow_accounts.update().where(escrow_accounts.c.id == acct["id"])
                             .values(balance_cents=acct["balance_cents"] + t["amount_cents"]))
                conn.execute(escrow_ledger.insert().values(account_id=acct["id"], amount_cents=t["amount_cents"],
                                                           order_id=o["id"], note=f"Void {number}", by_user=actor))
    conn.execute(orders.update().where(orders.c.id == o["id"]).values(status="void"))
    audit(conn, actor, "order.void", "order", number, {"reason": reason})
    return get(conn, number)
