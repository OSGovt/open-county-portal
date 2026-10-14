"""Paying online: bill lookup, cart, checkout, processor return, receipts."""
from __future__ import annotations

import secrets
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select

from .. import cart as cart_mod, config_store, fees as fee_mod, notify, orders as order_mod, payments
from ..db import get_engine, offices, receivables, tx
from ..settings import get_settings
from ..web import client_ip, flash, money, parse_money, render, verify_csrf

router = APIRouter()

KINDS = {
    "property_tax": ("Property tax", "Account number or property address", "Printed at the top of your tax statement."),
    "court": ("Court fines and fees", "Case or citation number, or your name", "Printed on your citation or court notice."),
    "utility": ("Utility bill", "Account number or service address", "Printed on your bill."),
    "permit": ("Permit fees", "Permit number or address", "Printed on your permit notice."),
    "other": ("Other bills", "Account or reference number", ""),
}


@router.get("/pay", include_in_schema=False)
def pay_home(request: Request):
    with get_engine().connect() as conn:
        present = set(conn.execute(select(receivables.c.kind).distinct()).scalars())
        kinds = [(k, v[0]) for k, v in KINDS.items() if k in present]
        return render(request, "public/pay.html", conn, page_title="Pay", nav="pay", kinds=kinds)


@router.get("/pay/{kind}", include_in_schema=False)
def lookup(request: Request, kind: str, q: str = ""):
    if kind not in KINDS:
        raise HTTPException(404)
    title, label, hint = KINDS[kind]
    q = q.strip()[:120]
    error = None
    matches = []
    with get_engine().connect() as conn:
        if "q" in request.query_params:
            if len(q) < 3:
                error = "Enter at least 3 characters."
            else:
                like = f"%{q}%"
                matches = conn.execute(select(receivables).where(
                    receivables.c.kind == kind,
                    or_(receivables.c.account == q, receivables.c.account.ilike(like), receivables.c.name.ilike(like),
                        receivables.c.address.ilike(like)))
                    .order_by(receivables.c.account).limit(10)).mappings().all()
        return render(request, "public/pay_lookup.html", conn, page_title=f"Pay {title.lower()}", nav="pay", kind=kind,
                      title=title, label=label, hint=hint, q=q, error=error, matches=matches,
                      searched="q" in request.query_params)


@router.post("/cart/add", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def cart_add(request: Request):
    form = await request.form()
    kind = form.get("kind")
    back = "/cart"
    try:
        with get_engine().connect() as conn:
            if kind == "receivable":
                r = conn.execute(select(receivables).where(receivables.c.id == int(form.get("receivable_id", 0)))).mappings().first()
                if r is None:
                    raise ValueError("That bill could not be found.")
                amount = r["amount_due_cents"]
                if form.get("amount_choice") == "partial":
                    if not r["allow_partial"]:
                        raise ValueError("This bill must be paid in full.")
                    amount = parse_money(str(form.get("partial_amount", "")))
                    if amount is None or amount <= 0 or amount > r["amount_due_cents"]:
                        flash(request, f"Enter an amount between $0.01 and {money(r['amount_due_cents'])}.", "error")
                        return RedirectResponse(f"/pay/{r['kind']}?q={urllib.parse.quote(r['account'])}", status_code=303)
                if amount <= 0:
                    raise ValueError("This bill has no balance due.")
                cart_mod.add(request.session, cart_mod.new_item(kind="receivable", receivable_id=r["id"], amount_cents=amount))
                flash(request, f"Payment of {money(amount)} for account {r['account']} added to your cart.")
            elif kind == "certified_copy":
                fmt = "paper" if form.get("format") == "paper" else "electronic"
                cart_mod.add(request.session, cart_mod.new_item(kind="certified_copy", instrument=str(form.get("instrument")),
                                                                format=fmt))
                flash(request, f"Certified copy of {form.get('instrument')} added to your cart.")
            elif kind == "fee":
                f = fee_mod.current(conn, str(form.get("fee_code")))
                if f is None:
                    raise ValueError("That fee isn't available.")
                qty = max(1, min(99, int(form.get("qty", 1) or 1)))
                cart_mod.add(request.session, cart_mod.new_item(kind="fee", fee_code=f["code"], qty=qty))
                flash(request, f"{f['label']} added to your cart.")
            else:
                raise ValueError("Unknown item.")
    except ValueError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(back, status_code=303)


@router.post("/cart/remove", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def cart_remove(request: Request):
    form = await request.form()
    cart_mod.remove(request.session, str(form.get("item_id", "")))
    flash(request, "Item removed from your cart.")
    return RedirectResponse("/cart", status_code=303)


def _priced(conn, request):
    return cart_mod.price(conn, request.session.get("cart", []))


@router.get("/cart", include_in_schema=False)
def cart_page(request: Request):
    with get_engine().connect() as conn:
        priced = _priced(conn, request)
        return render(request, "public/cart.html", conn, page_title="Your cart", nav="cart", priced=priced,
                      grouped=_group(priced))


def _group(priced):
    groups: dict[str, list] = {}
    for l in priced.lines:
        groups.setdefault(l.item_id, []).append(l)
    return list(groups.values())


def _methods(conn, subtotal: int) -> list[dict]:
    policy = config_store.get(conn, "payments")
    adapter = payments.get(policy.get("processor") or "test")
    if adapter.code == "manual":
        return [{"code": "manual", "label": "Pay at the office or by mail", "fee": 0}]
    labels = {"card": "Credit or debit card", "wallet": "Apple Pay or Google Pay", "ach": "eCheck from a bank account"}
    out = []
    for m in policy.get("methods") or ["card"]:
        if m in labels:
            out.append({"code": m, "label": labels[m], "fee": fee_mod.card_fee(policy, subtotal, m),
                        "fee_label": fee_mod.fee_label(policy, m)})
    return out


@router.get("/checkout", include_in_schema=False)
def checkout_page(request: Request):
    with get_engine().connect() as conn:
        priced = _priced(conn, request)
        if not priced.lines:
            flash(request, "Your cart is empty.", "warning")
            return RedirectResponse("/cart", status_code=303)
        policy = config_store.get(conn, "payments")
        adapter = payments.get(policy.get("processor") or "test")
        return render(request, "public/checkout.html", conn, page_title="Checkout", nav="cart", priced=priced,
                      methods=_methods(conn, priced.subtotal), errors={}, values={}, is_test=adapter.is_test,
                      fee_authority=policy.get("fee_authority"))


@router.post("/checkout", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def checkout_submit(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    method = str(form.get("method", ""))
    errors = {}
    if "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Enter an email address for your receipt, like name@example.com."
    with tx() as conn:
        priced = _priced(conn, request)
        if not priced.lines:
            flash(request, "Your cart is empty.", "warning")
            return RedirectResponse("/cart", status_code=303)
        methods = _methods(conn, priced.subtotal)
        chosen = next((m for m in methods if m["code"] == method), None)
        if chosen is None:
            errors["method"] = "Choose how you want to pay."
        policy = config_store.get(conn, "payments")
        adapter = payments.get(policy.get("processor") or "test")
        if errors:
            return render(request, "public/checkout.html", conn, status_code=400, page_title="Checkout", nav="cart",
                          priced=priced, methods=methods, errors=errors, values={"email": email, "method": method},
                          is_test=adapter.is_test, fee_authority=policy.get("fee_authority"))
        order = order_mod.create(conn, priced, channel="online", method=method, fee_cents=chosen["fee"], email=email,
                                 processor=adapter.code)
        merchant = {r.slug: r.merchant_account for r in conn.execute(select(offices.c.slug, offices.c.merchant_account))}
        splits = [payments.SplitLine(o, merchant.get(o), amt) for o, amt in order_mod.by_office(order).items()]
    base = get_settings().site_url
    result = adapter.start(order=order, splits=splits, return_url=f"{base}/checkout/return/{adapter.code}",
                           cancel_url=f"{base}/checkout/cancel?order={order['number']}",
                           settings=policy.get("processor_settings") or {})
    request.session["last_order"] = {"number": order["number"], "token": order["token"]}
    if result.redirect_url:
        return RedirectResponse(result.redirect_url, status_code=303)
    request.session["cart"] = []
    flash(request, "Your order is saved. Bring the order number to the office, or mail payment with it.", "warning")
    return RedirectResponse(f"/receipt/{order['number']}?t={order['token']}", status_code=303)


@router.get("/checkout/return/{processor}", include_in_schema=False)
def checkout_return(request: Request, processor: str):
    adapter = payments.get(processor)
    params = dict(request.query_params)
    with tx() as conn:
        policy = config_store.get(conn, "payments")
        result = adapter.confirm(params=params, settings=policy.get("processor_settings") or {})
        order = order_mod.get(conn, result.order_number)
        if order is None:
            raise HTTPException(404)
        if not result.ok:
            order_mod.mark_failed(conn, order["number"], result.message)
            flash(request, f"{result.message} Your cart is still saved; you can try again.", "error")
            return RedirectResponse("/cart", status_code=303)
        if result.amount_cents < order["total_cents"]:
            order_mod.mark_failed(conn, order["number"], "Amount mismatch")
            flash(request, "The payment amount didn't match the order. No charge was recorded; contact the office.", "error")
            return RedirectResponse(f"/receipt/{order['number']}?t={order['token']}", status_code=303)
        paid = order_mod.mark_paid(conn, order["number"], [{"kind": result.method, "amount_cents": result.amount_cents,
                                                            "detail": f"{adapter.name} {result.processor_ref or ''}".strip()}],
                                   processor_ref=result.processor_ref, actor=f"processor:{processor}")
    request.session["cart"] = []
    _email_receipt(paid)
    return RedirectResponse(f"/receipt/{paid['number']}?t={paid['token']}", status_code=303)


@router.get("/checkout/cancel", include_in_schema=False)
def checkout_cancel(request: Request, order: str = ""):
    with tx() as conn:
        o = order_mod.get(conn, order)
        if o and o["status"] == "pending":
            from ..db import orders as orders_table
            conn.execute(orders_table.update().where(orders_table.c.id == o["id"]).values(status="cancelled"))
    flash(request, "Payment cancelled. Nothing was charged.", "warning")
    return RedirectResponse("/cart", status_code=303)


@router.get("/receipt/{number}", include_in_schema=False)
def receipt(request: Request, number: str, t: str = ""):
    with get_engine().connect() as conn:
        o = order_mod.get(conn, number)
        if o is None or not secrets.compare_digest(o["token"], t or ""):
            raise HTTPException(404)
        names = {r.slug: r.name for r in conn.execute(select(offices.c.slug, offices.c.name))}
        split = [(names.get(k, k), v) for k, v in order_mod.by_office(o).items()]
        policy = config_store.get(conn, "payments")
        return render(request, "public/receipt.html", conn, page_title=f"Receipt {number}", o=o, split=split,
                      fee_label=fee_mod.fee_label(policy, o["method"] or ""))


def _email_receipt(o: dict) -> None:
    lines = [f"Receipt {o['number']}", ""]
    for l in o["lines"]:
        lines.append(f"{l['label']}: {money(l['amount_cents'])}")
    if o["fee_cents"]:
        lines.append(f"Processing fee: {money(o['fee_cents'])}")
    lines += ["", f"Total paid: {money(o['total_cents'])}",
              f"View your receipt: {get_settings().site_url}/receipt/{o['number']}?t={o['token']}"]
    notify.send(o.get("email"), f"Receipt {o['number']}", "\n".join(lines))


# ---- built-in TEST processor's hosted page -----------------------------------

@router.get("/payments/test/pay", include_in_schema=False)
def test_pay_page(request: Request, order: str, amount: int):
    with get_engine().connect() as conn:
        o = order_mod.get(conn, order)
        if o is None or o["total_cents"] != amount:
            raise HTTPException(404)
        return render(request, "public/test_processor.html", conn, page_title="TEST payment", o=o,
                      return_url=request.query_params.get("return", "/checkout/return/test"),
                      cancel_url=request.query_params.get("cancel", "/cart"), error=None)


@router.post("/payments/test/pay", include_in_schema=False, dependencies=[Depends(verify_csrf)])
async def test_pay_submit(request: Request):
    from ..payments.test_processor import APPROVE, DECLINE, sign
    form = await request.form()
    order = str(form.get("order"))
    card = "".join(ch for ch in str(form.get("card", "")) if ch.isdigit())
    with get_engine().connect() as conn:
        o = order_mod.get(conn, order)
        if o is None:
            raise HTTPException(404)
        if card not in (APPROVE, DECLINE):
            return render(request, "public/test_processor.html", conn, status_code=400, page_title="TEST payment", o=o,
                          return_url=str(form.get("return")), cancel_url=str(form.get("cancel")),
                          error="Use a test card number: 4242 4242 4242 4242 to approve, or 4000 0000 0000 0002 to decline.")
    status = "approved" if card == APPROVE else "declined"
    ref = f"TEST-{secrets.token_hex(5).upper()}"
    params = {"order": o["number"], "amount": o["total_cents"], "status": status, "ref": ref,
              "method": "card", "sig": sign(o["number"], o["total_cents"], status, ref)}
    return_url = str(form.get("return") or "/checkout/return/test")
    path = urllib.parse.urlparse(return_url).path or "/checkout/return/test"
    return RedirectResponse(f"{path}?{urllib.parse.urlencode(params)}", status_code=303)
