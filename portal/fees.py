"""Fee engine: the one place amounts come from.

Fees are rows with an effective date. A change adopted by the governing body
is entered with its future effective date and takes over on that day, so the
published fee, the counter price and the receipt can never disagree.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, or_, select
from sqlalchemy.engine import Connection

from .db import fees


def current(conn: Connection, code: str, on: dt.date | None = None) -> dict | None:
    on = on or dt.date.today()
    row = conn.execute(select(fees).where(
        fees.c.code == code, fees.c.effective_from <= on,
        or_(fees.c.effective_to.is_(None), fees.c.effective_to >= on))
        .order_by(fees.c.effective_from.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def all_current(conn: Connection, on: dt.date | None = None, office: str | None = None,
                counter_only: bool = False) -> list[dict]:
    on = on or dt.date.today()
    cond = [fees.c.effective_from <= on, or_(fees.c.effective_to.is_(None), fees.c.effective_to >= on)]
    if office:
        cond.append(fees.c.office_slug == office)
    if counter_only:
        cond.append(fees.c.counter.is_(True))
    rows = conn.execute(select(fees).where(and_(*cond)).order_by(fees.c.office_slug, fees.c.label,
                                                                   fees.c.effective_from.desc())).mappings().all()
    seen, out = set(), []
    for r in rows:
        if r["code"] in seen:
            continue
        seen.add(r["code"])
        out.append(dict(r))
    return out


def scheduled(conn: Connection) -> list[dict]:
    """Fee changes that take effect in the future."""
    return [dict(r) for r in conn.execute(select(fees).where(fees.c.effective_from > dt.date.today())
                                          .order_by(fees.c.effective_from)).mappings()]


def unconfirmed_count(conn: Connection) -> int:
    return len([f for f in all_current(conn) if not f["confirmed"]])


def card_fee(policy: dict, subtotal_cents: int, method: str) -> int:
    """Processing fee for a payment method, under the policy the governing body set."""
    if subtotal_cents <= 0:
        return 0
    if method == "ach":
        return int(policy.get("ach_fee_flat_cents") or 0)
    if method in ("card", "wallet"):
        pct = float(policy.get("card_fee_percent") or 0)
        flat = int(policy.get("card_fee_flat_cents") or 0)
        minimum = int(policy.get("card_fee_min_cents") or 0)
        fee = round(subtotal_cents * pct / 100) + flat
        if fee and fee < minimum:
            fee = minimum
        return fee
    return 0


def fee_label(policy: dict, method: str) -> str:
    if method == "ach":
        return "eCheck processing fee"
    if method in ("card", "wallet"):
        pct = float(policy.get("card_fee_percent") or 0)
        parts = []
        if pct:
            parts.append(f"{pct:g}%")
        if policy.get("card_fee_flat_cents"):
            parts.append(f"${int(policy['card_fee_flat_cents']) / 100:.2f}")
        return "Card processing fee" + (f" ({' + '.join(parts)})" if parts else "")
    return "Processing fee"
