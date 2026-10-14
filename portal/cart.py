"""The cart: items held in the visitor's signed session cookie.

Only references and quantities are stored in the cookie. Every amount is
recomputed from the fee table and receivables each time the cart is shown
or paid, so a cart can't be tampered with and always reflects current fees.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.engine import Connection

from . import config_store, fees as fee_mod, records as rec_mod
from .db import applications, offices, receivables

MAX_ITEMS = 50


@dataclass
class Line:
    item_id: str
    office_slug: str
    office_name: str
    kind: str
    fee_code: str | None
    label: str
    qty: int
    unit_cents: int
    amount_cents: int
    statute: str | None
    fund: str | None
    ref: str | None
    fulfil: bool = False


@dataclass
class Priced:
    lines: list[Line] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> int:
        return sum(l.amount_cents for l in self.lines)

    def by_office(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for l in self.lines:
            out[l.office_name] = out.get(l.office_name, 0) + l.amount_cents
        return out


def new_item(**kw) -> dict:
    kw["id"] = secrets.token_hex(4)
    return kw


def add(session: dict, item: dict) -> None:
    cart = session.setdefault("cart", [])
    if len(cart) >= MAX_ITEMS:
        raise ValueError("Your cart is full. Check out, then start a new cart.")
    cart.append(item)
    session["cart"] = cart


def remove(session: dict, item_id: str) -> None:
    session["cart"] = [i for i in session.get("cart", []) if i.get("id") != item_id]


def _office_names(conn: Connection) -> dict[str, str]:
    return {r.slug: r.name for r in conn.execute(select(offices.c.slug, offices.c.name))}


def price(conn: Connection, items: list[dict]) -> Priced:
    names = _office_names(conn)
    out = Priced()
    rconf = config_store.get(conn, "records")
    for it in items:
        kind = it.get("kind")
        if kind == "fee":
            f = fee_mod.current(conn, it["fee_code"])
            if f is None:
                out.problems.append(f"'{it.get('label', it['fee_code'])}' is no longer offered and was left out.")
                continue
            qty = max(1, min(999, int(it.get("qty", 1))))
            out.lines.append(Line(it["id"], f["office_slug"], names.get(f["office_slug"], f["office_slug"]), "fee",
                                  f["code"], it.get("label") or f["label"], qty, f["amount_cents"],
                                  f["amount_cents"] * qty, f["statute"], f["fund"], it.get("ref")))
        elif kind == "receivable":
            r = conn.execute(select(receivables).where(receivables.c.id == it["receivable_id"])).mappings().first()
            if r is None:
                out.problems.append("A bill in your cart could not be found and was left out.")
                continue
            amount = int(it["amount_cents"])
            if amount > r["amount_due_cents"]:
                amount = r["amount_due_cents"]
                out.problems.append(f"The amount for account {r['account']} was reduced to the current balance.")
            if amount <= 0:
                out.problems.append(f"Account {r['account']} has no balance due and was left out.")
                continue
            label = f"{r['description'] or r['kind'].replace('_', ' ').title()}, account {r['account']}"
            if amount < r["amount_due_cents"]:
                label += " (partial payment)"
            out.lines.append(Line(it["id"], r["office_slug"], names.get(r["office_slug"], r["office_slug"]),
                                  "receivable", r["fee_code"], label, 1, amount, amount, None, None, r["account"]))
        elif kind == "certified_copy":
            rec = rec_mod.get(conn, it["instrument"])
            cert = fee_mod.current(conn, rconf.get("certified_fee_code") or "cert")
            page = fee_mod.current(conn, rconf.get("certified_page_fee_code") or "copy_page")
            if rec is None or cert is None:
                out.problems.append("A certified copy in your cart is no longer available and was left out.")
                continue
            fmt = "certified PDF" if it.get("format") == "electronic" else "paper"
            pages = max(1, rec["page_count"])
            office = cert["office_slug"]
            out.lines.append(Line(it["id"], office, names.get(office, office), "certified_copy", cert["code"],
                                  f"Certification, {rec['doc_type']} {rec['instrument_number']} ({fmt})", 1,
                                  cert["amount_cents"], cert["amount_cents"], cert["statute"], cert["fund"],
                                  rec["instrument_number"], fulfil=True))
            if page:
                out.lines.append(Line(it["id"], page["office_slug"], names.get(page["office_slug"], page["office_slug"]),
                                      "certified_copy", page["code"],
                                      f"Copy pages, {rec['instrument_number']}", pages, page["amount_cents"],
                                      page["amount_cents"] * pages, page["statute"], page["fund"],
                                      rec["instrument_number"]))
        elif kind == "application":
            app = conn.execute(select(applications).where(applications.c.number == it["application"])).mappings().first()
            f = fee_mod.current(conn, it["fee_code"])
            if app is None or f is None:
                out.problems.append("An application fee in your cart could not be found and was left out.")
                continue
            out.lines.append(Line(it["id"], f["office_slug"], names.get(f["office_slug"], f["office_slug"]),
                                  "application", f["code"], f"{f['label']} (application {app['number']})", 1,
                                  f["amount_cents"], f["amount_cents"], f["statute"], f["fund"], app["number"]))
    return out
