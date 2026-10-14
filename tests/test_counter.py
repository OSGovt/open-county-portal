"""Staff sign-in and the counter point of sale."""
from __future__ import annotations

import re

from sqlalchemy import select

from portal.db import drawer_sessions, orders, tx

from .conftest import csrf, staff_login


def test_staff_pages_require_login(client):
    r = client.get("/staff/", follow_redirects=False)
    assert r.status_code == 303 and "/staff/login" in r.headers["location"]


def test_wrong_password_is_generic(client):
    token = csrf(client, "/staff/login")
    r = client.post("/staff/login", data={"_csrf": token, "email": "admin@test.gov", "password": "nope", "next": "/staff"})
    assert r.status_code == 400 and "match an active account" in r.text


def test_counter_cash_sale_and_close(client):
    staff_login(client)
    assert "Staff dashboard" in client.get("/staff/").text or "Good to see you" in client.get("/staff/").text
    page = client.get("/staff/counter").text
    assert "Open a drawer" in page
    token = csrf(client, "/staff/counter")
    r = client.post("/staff/counter/open", data={"_csrf": token, "drawer_id": "new", "office_slug": "county-clerk",
                                                 "opening": "200.00"}, follow_redirects=True)
    assert "Drawer opened" in r.text
    token = csrf(client, "/staff/counter")
    client.post("/staff/counter/add", data={"_csrf": token, "kind": "fee", "fee_code": "rec_first", "qty": "1"})
    client.post("/staff/counter/add", data={"_csrf": token, "kind": "fee", "fee_code": "rec_addl", "qty": "3"})
    client.post("/staff/counter/add", data={"_csrf": token, "kind": "fee", "fee_code": "records_mgmt", "qty": "1"})
    page = client.get("/staff/counter").text
    assert "$27.00" in page  # 5 + 3*4 + 10
    r = client.post("/staff/counter/complete", data={"_csrf": token, "tender": "cash", "cash_given": "20.00"},
                    follow_redirects=True)
    assert "Cash given must be at least $27.00" in r.text
    r = client.post("/staff/counter/complete", data={"_csrf": token, "tender": "cash", "cash_given": "30.00",
                                                     "reference": "Deed for J Q Resident"}, follow_redirects=True)
    assert "Give change: $3.00" in r.text
    number = re.search(r"Sale (CC-\d{4}-\d{5}) complete", r.text).group(1)
    assert "Receipt" in client.get(f"/staff/counter/receipt/{number}").text
    client.post("/staff/counter/add", data={"_csrf": token, "kind": "fee", "fee_code": "copy_page", "qty": "4"})
    r = client.post("/staff/counter/complete", data={"_csrf": token, "tender": "check", "check_number": "1042"},
                    follow_redirects=True)
    assert "complete" in r.text
    close = client.get("/staff/counter/close").text
    assert "$227.00" in close  # 200 opening + 27 cash
    token = csrf(client, "/staff/counter/close")
    r = client.post("/staff/counter/close", data={"_csrf": token, "counted": "226.00"}, follow_redirects=True)
    assert "variance of -$1.00" in r.text
    with tx() as conn:
        s = conn.execute(select(drawer_sessions).order_by(drawer_sessions.c.id.desc())).mappings().first()
        assert s["variance_cents"] == -100 and s["expected_cash_cents"] == 22700
        assert conn.execute(select(orders.c.status).where(orders.c.number == number)).scalar_one() == "paid"


def test_supervisor_void(client):
    staff_login(client)
    token = csrf(client, "/staff/counter")
    client.post("/staff/counter/open", data={"_csrf": token, "drawer_id": "new", "office_slug": "county-clerk",
                                             "opening": "0"})
    client.post("/staff/counter/add", data={"_csrf": token, "kind": "fee", "fee_code": "cert", "qty": "1"})
    r = client.post("/staff/counter/complete", data={"_csrf": token, "tender": "card"}, follow_redirects=True)
    number = re.search(r"Sale (CC-\d{4}-\d{5}) complete", r.text).group(1)
    token = csrf(client, "/staff/counter/close")
    r = client.post("/staff/counter/void", data={"_csrf": token, "number": number, "reason": "Customer changed mind"},
                    follow_redirects=True)
    assert "voided" in r.text
    with tx() as conn:
        assert conn.execute(select(orders.c.status).where(orders.c.number == number)).scalar_one() == "void"
