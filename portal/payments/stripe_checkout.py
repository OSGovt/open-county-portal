"""Stripe Checkout adapter (online card and wallet payments).

Residents pay on Stripe's hosted Checkout page; the portal never sees card
numbers. Settings (Staff console > Settings > Payments > Processor settings):

    secret_key: sk_live_...        (use sk_test_... until acceptance testing is done)
    currency: usd                  (optional)

How it works:
  start    creates a Checkout Session for the order total, with the order
           number as client_reference_id, and sends the resident to its URL
  confirm  looks the session up by id on Stripe's API (it does not trust the
           query string) and accepts it only if Stripe reports it paid
  refund   refunds the session's PaymentIntent, in full or in part

Limits, stated plainly:
  - One Stripe account receives the money. The finance report still splits
    every order by office for posting; Stripe Connect split settlement is
    not implemented.
  - Bank-account payments (ACH) settle days later and need a webhook this
    adapter doesn't have, so offer cards and wallets only with it.
  - No counter terminal integration; use a standalone terminal and record the
    payment at the counter as "card".
"""
from __future__ import annotations

import httpx

from . import PaymentResult, SplitLine, StartResult, register

API = "https://api.stripe.com/v1"
_transport: httpx.BaseTransport | None = None  # tests replace this with a mock


def _client(settings: dict) -> httpx.Client:
    key = (settings.get("secret_key") or "").strip()
    if not key.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
        raise ValueError("Stripe secret_key is missing or doesn't look like a Stripe key. "
                         "Add 'secret_key: sk_...' under Processor settings.")
    return httpx.Client(base_url=API, auth=(key, ""), timeout=30, transport=_transport,
                        headers={"Stripe-Version": "2024-06-20"})


def _error(resp: httpx.Response) -> str:
    try:
        return resp.json().get("error", {}).get("message", "") or resp.text[:200]
    except ValueError:
        return resp.text[:200]


class StripeCheckout:
    code = "stripe"
    name = "Stripe Checkout"
    is_test = False
    supports_online = True
    supports_terminal = False

    def start(self, *, order: dict, splits: list[SplitLine], return_url: str, cancel_url: str,
              settings: dict) -> StartResult:
        currency = (settings.get("currency") or "usd").lower()
        data = {
            "mode": "payment",
            "client_reference_id": order["number"],
            "success_url": f"{return_url}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": cancel_url,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency,
            "line_items[0][price_data][unit_amount]": str(order["total_cents"]),
            "line_items[0][price_data][product_data][name]": f"Order {order['number']}",
            "metadata[order_number]": order["number"],
            "payment_intent_data[metadata][order_number]": order["number"],
        }
        if order.get("email"):
            data["customer_email"] = order["email"]
        for i, s in enumerate(splits):  # recorded on the payment for reconciliation
            data[f"payment_intent_data[metadata][office_{i}]"] = f"{s.office_slug}:{s.amount_cents}"
        with _client(settings) as c:
            resp = c.post("/checkout/sessions", data=data, headers={"Idempotency-Key": f"start-{order['number']}"})
        if resp.status_code != 200:
            raise RuntimeError(f"Stripe didn't create a payment page: {_error(resp)}")
        body = resp.json()
        return StartResult(redirect_url=body["url"], processor_ref=body["id"])

    def confirm(self, *, params: dict, settings: dict) -> PaymentResult:
        session_id = params.get("session_id", "")
        if not session_id.startswith("cs_"):
            return PaymentResult(False, params.get("order", ""), None, 0, "card",
                                 "The payment response could not be verified.")
        with _client(settings) as c:
            resp = c.get(f"/checkout/sessions/{session_id}")
        if resp.status_code != 200:
            return PaymentResult(False, "", None, 0, "card", "The payment response could not be verified.")
        s = resp.json()
        number = s.get("client_reference_id") or (s.get("metadata") or {}).get("order_number", "")
        amount = int(s.get("amount_total") or 0)
        method = "card"
        types = s.get("payment_method_types") or []
        if types and types[0] not in ("card", "link"):
            method = types[0]
        if s.get("status") == "complete" and s.get("payment_status") == "paid":
            return PaymentResult(True, number, s.get("payment_intent"), amount, method)
        if s.get("status") == "complete" and s.get("payment_status") == "unpaid":
            return PaymentResult(False, number, s.get("payment_intent"), amount, method,
                                 "Your payment is still processing. Contact the office before paying again.")
        return PaymentResult(False, number, s.get("payment_intent"), amount, method,
                             "The payment wasn't completed. No charge was made.")

    def refund(self, *, order: dict, amount_cents: int, settings: dict) -> PaymentResult:
        intent = order.get("processor_ref") or ""
        if not intent.startswith("pi_"):
            return PaymentResult(False, order["number"], None, amount_cents, "card",
                                 "This order has no Stripe payment to refund.")
        with _client(settings) as c:
            resp = c.post("/refunds", data={"payment_intent": intent, "amount": str(amount_cents)},
                          headers={"Idempotency-Key": f"refund-{order['number']}-{amount_cents}"})
        if resp.status_code != 200:
            return PaymentResult(False, order["number"], None, amount_cents, "card", f"Refund failed: {_error(resp)}")
        body = resp.json()
        ok = body.get("status") in ("succeeded", "pending")
        return PaymentResult(ok, order["number"], body.get("id"), amount_cents, "card",
                             "" if ok else f"Refund status: {body.get('status')}")

    def terminal_charge(self, *, order: dict, terminal_id: str, settings: dict) -> PaymentResult:
        return PaymentResult(False, order["number"], None, order["total_cents"], "card",
                             "Stripe terminals aren't connected. Run the card on the terminal and record it as card.")


register(StripeCheckout())
