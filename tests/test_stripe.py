"""Stripe Checkout adapter against a mocked Stripe API (no network)."""
from __future__ import annotations

import json
import urllib.parse

import httpx
import pytest

from portal.payments import SplitLine, stripe_checkout

SETTINGS = {"secret_key": "sk_test_123"}
calls: list[httpx.Request] = []


def handler(request: httpx.Request) -> httpx.Response:
    calls.append(request)
    path = request.url.path
    if request.method == "POST" and path == "/v1/checkout/sessions":
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        assert form["line_items[0][price_data][unit_amount]"] == "2575"
        assert form["client_reference_id"] == "OC-2026-00001"
        assert form["success_url"].endswith("?session_id={CHECKOUT_SESSION_ID}")
        assert request.headers["Idempotency-Key"] == "start-OC-2026-00001"
        return httpx.Response(200, json={"id": "cs_test_abc", "url": "https://checkout.stripe.com/c/pay/cs_test_abc"})
    if request.method == "GET" and path == "/v1/checkout/sessions/cs_test_paid":
        return httpx.Response(200, json={"id": "cs_test_paid", "status": "complete", "payment_status": "paid",
                                         "amount_total": 2575, "client_reference_id": "OC-2026-00001",
                                         "payment_intent": "pi_123", "payment_method_types": ["card"]})
    if request.method == "GET" and path == "/v1/checkout/sessions/cs_test_open":
        return httpx.Response(200, json={"id": "cs_test_open", "status": "open", "payment_status": "unpaid",
                                         "amount_total": 2575, "client_reference_id": "OC-2026-00001"})
    if request.method == "POST" and path == "/v1/refunds":
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        assert form == {"payment_intent": "pi_123", "amount": "2575"}
        return httpx.Response(200, json={"id": "re_1", "status": "succeeded"})
    return httpx.Response(404, json={"error": {"message": "No such object"}})


@pytest.fixture(autouse=True)
def mock_stripe():
    calls.clear()
    stripe_checkout._transport = httpx.MockTransport(handler)
    yield
    stripe_checkout._transport = None


ADAPTER = stripe_checkout.StripeCheckout()
ORDER = {"number": "OC-2026-00001", "total_cents": 2575, "email": "res@example.com", "processor_ref": "pi_123"}


def test_start_sends_resident_to_hosted_page():
    r = ADAPTER.start(order=ORDER, splits=[SplitLine("tax-office", None, 2575)],
                      return_url="https://portal.example.gov/checkout/return/stripe",
                      cancel_url="https://portal.example.gov/checkout/cancel?order=OC-2026-00001", settings=SETTINGS)
    assert r.redirect_url.startswith("https://checkout.stripe.com/")
    assert calls[0].headers["Authorization"].startswith("Basic ")


def test_confirm_looks_session_up_on_stripe():
    r = ADAPTER.confirm(params={"session_id": "cs_test_paid"}, settings=SETTINGS)
    assert r.ok and r.order_number == "OC-2026-00001" and r.amount_cents == 2575 and r.processor_ref == "pi_123"
    r = ADAPTER.confirm(params={"session_id": "cs_test_open"}, settings=SETTINGS)
    assert not r.ok and "No charge" in r.message
    r = ADAPTER.confirm(params={"session_id": "forged", "order": "OC-2026-00001"}, settings=SETTINGS)
    assert not r.ok and len(calls) == 2  # a forged id never reaches Stripe
    r = ADAPTER.confirm(params={"session_id": "cs_unknown"}, settings=SETTINGS)
    assert not r.ok


def test_refund_and_missing_key():
    assert ADAPTER.refund(order=ORDER, amount_cents=2575, settings=SETTINGS).ok
    with pytest.raises(ValueError):
        ADAPTER.start(order=ORDER, splits=[], return_url="x", cancel_url="y", settings={})
