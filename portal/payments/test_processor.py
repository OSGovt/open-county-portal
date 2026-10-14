"""Built-in TEST processor.

Simulates a real processor's hosted payment page so staff can be trained and
acceptance tests can run before a processor contract exists. No money moves
and no card number is stored. The page says TEST in large type, and the
staff console shows a warning on every page while this adapter is active.

Test card numbers:
  4242 4242 4242 4242  approved
  4000 0000 0000 0002  declined
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import urllib.parse

from ..settings import get_settings
from . import PaymentResult, SplitLine, StartResult, register

APPROVE = "4242424242424242"
DECLINE = "4000000000000002"


def sign(order_number: str, amount: int, status: str, ref: str) -> str:
    msg = f"{order_number}|{amount}|{status}|{ref}".encode()
    return hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()


class TestProcessor:
    code = "test"
    name = "Test processor (no real payments)"
    is_test = True
    supports_online = True
    supports_terminal = True

    def start(self, *, order: dict, splits: list[SplitLine], return_url: str, cancel_url: str,
              settings: dict) -> StartResult:
        params = urllib.parse.urlencode({"order": order["number"], "amount": order["total_cents"],
                                         "return": return_url, "cancel": cancel_url})
        return StartResult(redirect_url=f"/payments/test/pay?{params}")

    def confirm(self, *, params: dict, settings: dict) -> PaymentResult:
        order_number = params.get("order", "")
        amount = int(params.get("amount", "0") or 0)
        status = params.get("status", "")
        ref = params.get("ref", "")
        expected = sign(order_number, amount, status, ref)
        if not hmac.compare_digest(expected, params.get("sig", "")):
            return PaymentResult(False, order_number, None, amount, "card", "The payment response could not be verified.")
        if status != "approved":
            return PaymentResult(False, order_number, ref, amount, "card", "The card was declined. No charge was made.")
        return PaymentResult(True, order_number, ref, amount, params.get("method", "card"))

    def refund(self, *, order: dict, amount_cents: int, settings: dict) -> PaymentResult:
        return PaymentResult(True, order["number"], f"TEST-REFUND-{secrets.token_hex(4)}", amount_cents, order.get("method") or "card")

    def terminal_charge(self, *, order: dict, terminal_id: str, settings: dict) -> PaymentResult:
        return PaymentResult(True, order["number"], f"TEST-TERM-{secrets.token_hex(4)}", order["total_cents"], "card",
                             "Approved on test terminal")


register(TestProcessor())
