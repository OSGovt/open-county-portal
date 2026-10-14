"""Counter point of sale: drawers, sales, tenders, receipts, voids, close-out."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select

from ... import auth, cart as cart_mod, config_store, fees as fee_mod, orders as order_mod, payments
from ...db import (audit, drawer_sessions, drawers, escrow_accounts, get_engine, offices, orders, receivables, tenders,
                   tx, utcnow)
from ...web import client_ip, flash, money, parse_money, verify_csrf
from .common import staff_render

router = APIRouter(prefix="/counter")
KEY = "counter_cart"


def _open_session(conn, user: dict) -> dict | None:
    row = conn.execute(select(drawer_sessions, drawers.c.name.label("drawer_name"), drawers.c.office_slug)
                       .select_from(drawer_sessions.join(drawers, drawers.c.id == drawer_sessions.c.drawer_id))
                       .where(drawer_sessions.c.opened_by == user["email"], drawer_sessions.c.closed_at.is_(None))
                       ).mappings().first()
    return dict(row) if row else None


def _user_offices(conn, user: dict) -> list[str]:
    if auth.has_role(user, "admin", "supervisor") and not user.get("offices"):
        return [r for r in conn.execute(select(offices.c.slug).where(offices.c.active.is_(True))).scalars()]
    return user.get("offices") or []


def _expected_cash(conn, session_id: int, opening: int) -> int:
    cash = conn.execute(select(func.coalesce(func.sum(tenders.c.amount_cents), 0))
                        .select_from(tenders.join(orders, orders.c.id == tenders.c.order_id))
                        .where(orders.c.drawer_session_id == session_id, orders.c.status == "paid",
                               tenders.c.kind == "cash")).scalar_one()
    return opening + int(cash)


@router.get("")
def counter(request: Request, q: str = "", bill: str = ""):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        sess = _open_session(conn, user)
        my_offices = _user_offices(conn, user)
        if sess is None:
            avail = conn.execute(select(drawers).where(drawers.c.active.is_(True), drawers.c.office_slug.in_(my_offices))
                                 .order_by(drawers.c.office_slug, drawers.c.name)).mappings().all()
            return staff_render(request, "staff/counter_open.html", conn, user, page_title="Open a drawer",
                                drawers=avail, my_offices=my_offices)
        fee_rows = [f for f in fee_mod.all_current(conn, counter_only=True) if f["office_slug"] in my_offices]
        if q:
            fee_rows = [f for f in fee_rows if q.lower() in (f["label"] + " " + (f["statute"] or "")).lower()]
        bills = []
        if bill.strip():
            like = f"%{bill.strip()}%"
            bills = conn.execute(select(receivables).where(
                receivables.c.office_slug.in_(my_offices),
                or_(receivables.c.account.ilike(like), receivables.c.name.ilike(like), receivables.c.address.ilike(like)))
                .limit(10)).mappings().all()
        priced = cart_mod.price(conn, request.session.get(KEY, []))
        policy = config_store.get(conn, "payments")
        escrows = conn.execute(select(escrow_accounts).where(escrow_accounts.c.active.is_(True))
                               .order_by(escrow_accounts.c.name)).mappings().all()
        card_fee = fee_mod.card_fee(policy, priced.subtotal, "card")
        last = request.session.pop("counter_last", None)
        return staff_render(request, "staff/counter.html", conn, user, page_title="Counter", sess=sess, fees=fee_rows,
                            q=q, bill=bill, bills=bills, priced=priced, escrows=escrows, card_fee=card_fee,
                            card_fee_label=fee_mod.fee_label(policy, "card"), last=last,
                            reference=request.session.get("counter_ref", ""))


@router.post("/open", dependencies=[Depends(verify_csrf)])
async def open_drawer(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        if _open_session(conn, user):
            return RedirectResponse("/staff/counter", status_code=303)
        drawer_id = form.get("drawer_id")
        if drawer_id == "new":
            office = str(form.get("office_slug", ""))
            if office not in _user_offices(conn, user):
                raise HTTPException(403, "You can't open a drawer for that office.")
            n = conn.execute(select(func.count()).select_from(drawers).where(drawers.c.office_slug == office)).scalar_one()
            drawer_id = conn.execute(drawers.insert().values(name=f"Drawer {n + 1}", office_slug=office)
                                     .returning(drawers.c.id)).scalar_one()
        opening = parse_money(str(form.get("opening", "0"))) or 0
        busy = conn.execute(select(drawer_sessions.c.id).where(drawer_sessions.c.drawer_id == int(drawer_id),
                                                               drawer_sessions.c.closed_at.is_(None))).first()
        if busy:
            flash(request, "That drawer is already open on another session. Choose another or ask a supervisor.", "error")
            return RedirectResponse("/staff/counter", status_code=303)
        sid = conn.execute(drawer_sessions.insert().values(drawer_id=int(drawer_id), opened_by=user["email"],
                                                           opening_cash_cents=opening).returning(drawer_sessions.c.id)).scalar_one()
        audit(conn, user["email"], "drawer.open", "drawer_session", sid, {"opening_cents": opening}, client_ip(request))
    flash(request, f"Drawer opened with {money(opening)} starting cash.")
    return RedirectResponse("/staff/counter", status_code=303)


@router.post("/add", dependencies=[Depends(verify_csrf)])
async def add_item(request: Request):
    form = await request.form()
    items = request.session.get(KEY, [])
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        if form.get("kind") == "fee":
            qty = max(1, min(999, int(form.get("qty", 1) or 1)))
            f = fee_mod.current(conn, str(form.get("fee_code")))
            if f is None or f["office_slug"] not in _user_offices(conn, user):
                raise HTTPException(403)
            items.append(cart_mod.new_item(kind="fee", fee_code=f["code"], qty=qty))
            msg = f"Added {qty} × {f['label']}."
        elif form.get("kind") == "receivable":
            r = conn.execute(select(receivables).where(receivables.c.id == int(form.get("receivable_id", 0)))).mappings().first()
            if r is None:
                raise HTTPException(404)
            amount = parse_money(str(form.get("amount", ""))) or r["amount_due_cents"]
            if amount > r["amount_due_cents"] or amount <= 0:
                flash(request, f"Enter an amount up to {money(r['amount_due_cents'])}.", "error")
                return RedirectResponse(f"/staff/counter?bill={r['account']}", status_code=303)
            items.append(cart_mod.new_item(kind="receivable", receivable_id=r["id"], amount_cents=amount))
            msg = f"Added {money(amount)} for account {r['account']}."
        else:
            raise HTTPException(400)
    request.session[KEY] = items
    if form.get("reference") is not None:
        request.session["counter_ref"] = str(form.get("reference"))
    flash(request, msg)
    return RedirectResponse("/staff/counter", status_code=303)


@router.post("/remove", dependencies=[Depends(verify_csrf)])
async def remove_item(request: Request):
    form = await request.form()
    request.session[KEY] = [i for i in request.session.get(KEY, []) if i.get("id") != form.get("item_id")]
    return RedirectResponse("/staff/counter", status_code=303)


@router.post("/clear", dependencies=[Depends(verify_csrf)])
async def clear(request: Request):
    request.session[KEY] = []
    request.session["counter_ref"] = ""
    flash(request, "Sale cleared.")
    return RedirectResponse("/staff/counter", status_code=303)


@router.post("/complete", dependencies=[Depends(verify_csrf)])
async def complete(request: Request):
    form = await request.form()
    tender = str(form.get("tender", ""))
    reference = str(form.get("reference", "")).strip() or None
    with tx() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        sess = _open_session(conn, user)
        if sess is None:
            flash(request, "Open a drawer first.", "error")
            return RedirectResponse("/staff/counter", status_code=303)
        priced = cart_mod.price(conn, request.session.get(KEY, []))
        if not priced.lines:
            flash(request, "Add at least one item first.", "error")
            return RedirectResponse("/staff/counter", status_code=303)
        policy = config_store.get(conn, "payments")
        fee = fee_mod.card_fee(policy, priced.subtotal, "card") if tender == "card" else 0
        total = priced.subtotal + fee
        tender_row: dict = {"kind": tender, "amount_cents": total}
        change = 0
        if tender == "cash":
            given = parse_money(str(form.get("cash_given", "")))
            if given is None or given < total:
                flash(request, f"Cash given must be at least {money(total)}.", "error")
                return RedirectResponse("/staff/counter", status_code=303)
            change = given - total
            tender_row["detail"] = f"Cash given {money(given)}, change {money(change)}"
        elif tender == "check":
            check_no = str(form.get("check_number", "")).strip()
            if not check_no:
                flash(request, "Enter the check number.", "error")
                return RedirectResponse("/staff/counter", status_code=303)
            tender_row["detail"] = f"Check #{check_no}"
        elif tender == "escrow":
            acct = conn.execute(select(escrow_accounts).where(escrow_accounts.c.id == int(form.get("escrow_id", 0) or 0),
                                                              escrow_accounts.c.active.is_(True))).mappings().first()
            if acct is None:
                flash(request, "Choose an escrow account.", "error")
                return RedirectResponse("/staff/counter", status_code=303)
            if acct["balance_cents"] < total:
                flash(request, f"{acct['name']} has {money(acct['balance_cents'])}, less than {money(total)}. "
                               "Take another payment method or ask them to add funds.", "error")
                return RedirectResponse("/staff/counter", status_code=303)
            tender_row["account_id"] = acct["id"]
        elif tender != "card":
            flash(request, "Choose how the customer is paying.", "error")
            return RedirectResponse("/staff/counter", status_code=303)
        order = order_mod.create(conn, priced, channel="counter", method=tender, fee_cents=fee, reference=reference,
                                 processor=policy.get("processor") if tender == "card" else None,
                                 staff_user=user["email"], drawer_session_id=sess["id"])
        processor_ref = None
        if tender == "card":
            adapter = payments.get(policy.get("processor") or "test")
            result = adapter.terminal_charge(order=order, terminal_id=str(form.get("terminal", "")),
                                             settings=policy.get("processor_settings") or {})
            if not result.ok:
                order_mod.mark_failed(conn, order["number"], result.message)
                flash(request, f"Card not approved: {result.message}", "error")
                return RedirectResponse("/staff/counter", status_code=303)
            processor_ref = result.processor_ref
            tender_row["detail"] = f"Terminal {result.processor_ref}"
        paid = order_mod.mark_paid(conn, order["number"], [tender_row], processor_ref=processor_ref, actor=user["email"])
    request.session[KEY] = []
    request.session["counter_ref"] = ""
    request.session["counter_last"] = {"number": paid["number"], "token": paid["token"], "total": paid["total_cents"],
                                       "change": change}
    flash(request, f"Sale {paid['number']} complete. {('Give change: ' + money(change)) if change else ''}".strip())
    return RedirectResponse("/staff/counter", status_code=303)


@router.get("/receipt/{number}")
def receipt(request: Request, number: str):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "cashier", "supervisor", "finance")
        o = order_mod.get(conn, number)
        if o is None:
            raise HTTPException(404)
        names = {r.slug: r.name for r in conn.execute(select(offices.c.slug, offices.c.name))}
        return staff_render(request, "staff/counter_receipt.html", conn, user, page_title=f"Receipt {number}", o=o,
                            names=names)


@router.get("/orders")
def pending_orders(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        rows = conn.execute(select(orders).where(orders.c.status == "pending", orders.c.processor == "manual")
                            .order_by(orders.c.created_at.desc()).limit(200)).mappings().all()
        return staff_render(request, "staff/counter_orders.html", conn, user, page_title="Orders awaiting payment",
                            rows=rows)


@router.post("/orders/{number}/pay", dependencies=[Depends(verify_csrf)])
async def pay_saved_order(request: Request, number: str):
    form = await request.form()
    tender = str(form.get("tender", "cash"))
    with tx() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        sess = _open_session(conn, user)
        if sess is None:
            flash(request, "Open a drawer first.", "error")
            return RedirectResponse("/staff/counter", status_code=303)
        o = order_mod.get(conn, number)
        if o is None or o["status"] != "pending":
            flash(request, "That order isn't waiting for payment.", "error")
            return RedirectResponse("/staff/counter/orders", status_code=303)
        conn.execute(orders.update().where(orders.c.id == o["id"]).values(drawer_session_id=sess["id"]))
        detail = f"Check #{form.get('check_number')}" if tender == "check" else None
        order_mod.mark_paid(conn, number, [{"kind": tender, "amount_cents": o["total_cents"], "detail": detail}],
                            actor=user["email"])
    flash(request, f"Order {number} marked paid.")
    return RedirectResponse(f"/staff/counter/receipt/{number}", status_code=303)


@router.post("/void", dependencies=[Depends(verify_csrf)])
async def void(request: Request):
    form = await request.form()
    number, reason = str(form.get("number", "")).strip(), str(form.get("reason", "")).strip()
    with tx() as conn:
        user = auth.require(request, conn, "supervisor")
        if not reason:
            flash(request, "Give a reason for the void.", "error")
            return RedirectResponse("/staff/counter/close", status_code=303)
        try:
            order_mod.void(conn, number, user["email"], reason)
        except (KeyError, ValueError) as exc:
            flash(request, f"Couldn't void: {exc}", "error")
            return RedirectResponse("/staff/counter/close", status_code=303)
    flash(request, f"Order {number} voided. Return any cash from the drawer.")
    return RedirectResponse("/staff/counter/close", status_code=303)


@router.get("/close")
def close_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        sess = _open_session(conn, user)
        summary = []
        expected = None
        if sess:
            expected = _expected_cash(conn, sess["id"], sess["opening_cash_cents"])
            summary = conn.execute(select(tenders.c.kind, func.count(), func.sum(tenders.c.amount_cents))
                                   .select_from(tenders.join(orders, orders.c.id == tenders.c.order_id))
                                   .where(orders.c.drawer_session_id == sess["id"], orders.c.status == "paid")
                                   .group_by(tenders.c.kind)).all()
        recent = conn.execute(select(drawer_sessions, drawers.c.name.label("drawer_name"))
                              .select_from(drawer_sessions.join(drawers, drawers.c.id == drawer_sessions.c.drawer_id))
                              .where(drawer_sessions.c.closed_at.is_not(None))
                              .order_by(drawer_sessions.c.closed_at.desc()).limit(20)).mappings().all()
        return staff_render(request, "staff/counter_close.html", conn, user, page_title="Close drawer", sess=sess,
                            expected=expected, summary=summary, recent=recent)


@router.post("/close", dependencies=[Depends(verify_csrf)])
async def close_submit(request: Request):
    form = await request.form()
    counted = parse_money(str(form.get("counted", "")))
    with tx() as conn:
        user = auth.require(request, conn, "cashier", "supervisor")
        sess = _open_session(conn, user)
        if sess is None:
            return RedirectResponse("/staff/counter", status_code=303)
        if counted is None:
            flash(request, "Enter the cash you counted, like 412.50.", "error")
            return RedirectResponse("/staff/counter/close", status_code=303)
        expected = _expected_cash(conn, sess["id"], sess["opening_cash_cents"])
        variance = counted - expected
        conn.execute(drawer_sessions.update().where(drawer_sessions.c.id == sess["id"]).values(
            closed_at=utcnow(), closed_by=user["email"], counted_cash_cents=counted, expected_cash_cents=expected,
            variance_cents=variance, close_note=str(form.get("note", "")).strip() or None))
        audit(conn, user["email"], "drawer.close", "drawer_session", sess["id"],
              {"expected": expected, "counted": counted, "variance": variance}, client_ip(request))
    if variance == 0:
        flash(request, "Drawer closed and balanced.")
    else:
        flash(request, f"Drawer closed with a variance of {money(variance)}. It is flagged for your supervisor.", "warning")
    return RedirectResponse("/staff/counter/close", status_code=303)
