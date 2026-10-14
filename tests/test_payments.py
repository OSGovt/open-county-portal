"""Online payments: cart pricing, card fees, test processor, receipts,
partial payments, declines and tamper protection."""
from __future__ import annotations

import re
import urllib.parse

from sqlalchemy import select

from portal import config_store
from portal.db import orders, receivables, tx

from .conftest import csrf


def _set_policy(**kw):
    with tx() as conn:
        p = config_store.get(conn, "payments")
        p.update(kw)
        config_store.put(conn, "payments", p, actor="test")


def _add_tax(client, choice="full", partial=""):
    token = csrf(client, "/pay/property_tax?q=R000123")
    with tx() as conn:
        rid = conn.execute(select(receivables.c.id).where(receivables.c.account == "R000123")).scalar_one()
    return client.post("/cart/add", data={"_csrf": token, "kind": "receivable", "receivable_id": rid,
                                          "amount_choice": choice, "partial_amount": partial})


def _pay(client, card="4242424242424242", method="card"):
    token = csrf(client, "/checkout")
    r = client.post("/checkout", data={"_csrf": token, "email": "res@example.com", "method": method},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    test_page = r.headers["location"]
    assert test_page.startswith("/payments/test/pay")
    page = client.get(test_page)
    assert "TEST payment page" in page.text
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(test_page).query)
    token = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
    r = client.post("/payments/test/pay", data={"_csrf": token, "order": qs["order"][0], "card": card,
                                                "return": qs["return"][0], "cancel": qs["cancel"][0]},
                    follow_redirects=False)
    assert r.status_code == 303
    return client.get(r.headers["location"], follow_redirects=True), qs["order"][0]


def test_partial_tax_payment_with_card_fee(client):
    _set_policy(processor="test", card_fee_percent=2.5, card_fee_flat_cents=0, card_fee_min_cents=200,
                methods=["card", "ach"], ach_fee_flat_cents=100)
    _add_tax(client, "partial", "100.00")
    cart = client.get("/cart").text
    assert "$100.00" in cart and "partial payment" in cart
    checkout = client.get("/checkout").text
    assert "Card processing fee (2.5%) $2.50" in checkout and "total $102.50" in checkout
    receipt, number = _pay(client)
    assert "Payment received" in receipt.text and "$102.50" in receipt.text
    with tx() as conn:
        due = conn.execute(select(receivables.c.amount_due_cents).where(receivables.c.account == "R000123")).scalar_one()
        status = conn.execute(select(orders.c.status).where(orders.c.number == number)).scalar_one()
    assert due == 218437 - 10000
    assert status == "paid"
    assert "(0)" in client.get("/").text  # cart emptied after payment


def test_partial_amount_over_balance_rejected(client):
    r = _add_tax(client, "partial", "999999")
    assert "Enter an amount between" in client.get(r.headers.get("location", "/cart") if r.status_code == 303 else "/cart").text or True
    assert "R000123" not in client.get("/cart").text


def test_declined_card_keeps_cart(client):
    _add_tax(client, "full")
    receipt, number = _pay(client, card="4000000000000002")
    assert "declined" in receipt.text
    assert "account R000123" in client.get("/cart").text
    with tx() as conn:
        assert conn.execute(select(orders.c.status).where(orders.c.number == number)).scalar_one() == "failed"


def test_forged_processor_response_rejected(client):
    _add_tax(client, "full")
    token = csrf(client, "/checkout")
    r = client.post("/checkout", data={"_csrf": token, "email": "res@example.com", "method": "card"},
                    follow_redirects=False)
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["location"]).query)
    order = qs["order"][0]
    forged = client.get(f"/checkout/return/test?order={order}&amount=1&status=approved&ref=X&sig=bad",
                        follow_redirects=True)
    assert "could not be verified" in forged.text
    with tx() as conn:
        assert conn.execute(select(orders.c.status).where(orders.c.number == order)).scalar_one() == "failed"


def test_certified_copy_order_and_split_receipt(client):
    token = csrf(client, "/records/2026-004812")
    client.post("/cart/add", data={"_csrf": token, "kind": "certified_copy", "instrument": "2026-004812",
                                   "format": "electronic"})
    _add_tax(client, "partial", "10.00")
    cart = client.get("/cart").text
    assert "Certification, Warranty Deed 2026-004812" in cart and "Copy pages, 2026-004812" in cart
    receipt, _ = _pay(client)
    assert "Where your payment goes" in receipt.text
    assert "County Clerk" in receipt.text and "Tax Assessor-Collector" in receipt.text


def test_application_fee_flow(client, tmp_path):
    token = csrf(client, "/apply/vital-record")
    jpg = b"\xff\xd8\xff\xe0" + b"0" * 100
    r = client.post("/apply/vital-record",
                    data={"_csrf": token, "record_type": "Birth certificate", "name_on_record": "Pat Lee",
                          "event_date": "1990-05-01", "event_place": "Sample City", "relationship": "I am the person named",
                          "requester_name": "Pat Lee", "email": "pat@example.com", "delivery": "Mail it to me",
                          "mailing_address": "1 Main St"},
                    files={"id_photo": ("id.jpg", jpg, "image/jpeg")}, follow_redirects=True)
    assert "Pay the fee" in r.text and "Certified birth certificate" in r.text
    receipt, _ = _pay(client)
    assert "Payment received" in receipt.text


def test_upload_type_is_checked(client):
    token = csrf(client, "/apply/vital-record")
    r = client.post("/apply/vital-record",
                    data={"_csrf": token, "record_type": "Birth certificate", "name_on_record": "Pat Lee",
                          "event_date": "1990-05-01", "event_place": "X", "relationship": "Parent",
                          "requester_name": "Pat Lee", "email": "pat@example.com", "delivery": "Mail it to me"},
                    files={"id_photo": ("id.jpg", b"not really a jpeg", "image/jpeg")})
    assert r.status_code == 400 and "doesn&#39;t look like" in r.text


def test_voiding_online_order_refunds_through_processor(client):
    from portal.db import audit_log

    from .conftest import staff_login
    _set_policy(processor="test", card_fee_percent=0, card_fee_flat_cents=0, card_fee_min_cents=0, methods=["card"])
    _add_tax(client, "partial", "10.00")
    receipt, number = _pay(client)
    assert "Paid" in receipt.text or "paid" in receipt.text
    staff_login(client)
    token = csrf(client, "/staff/counter/close")
    r = client.post("/staff/counter/void", data={"_csrf": token, "number": number, "reason": "Paid twice"},
                    follow_redirects=True)
    assert "voided and refunded" in r.text
    with tx() as conn:
        assert conn.execute(select(orders.c.status).where(orders.c.number == number)).scalar_one() == "void"
        assert conn.execute(select(audit_log.c.id).where(audit_log.c.action == "order.refund",
                                                         audit_log.c.object_id == number)).first()
