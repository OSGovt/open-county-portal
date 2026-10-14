"""'Pay at the office' adapter.

For a jurisdiction that has not connected a processor yet. Online orders are
saved as unpaid with a reference number; the resident pays at the counter or
by mail, and staff mark the order paid in the counter screen.
"""
from __future__ import annotations

from . import PaymentResult, SplitLine, StartResult, register


class ManualPayment:
    code = "manual"
    name = "Pay at the office or by mail (no online card payments)"
    is_test = False
    supports_online = True
    supports_terminal = False

    def start(self, *, order: dict, splits: list[SplitLine], return_url: str, cancel_url: str,
              settings: dict) -> StartResult:
        return StartResult(completed=False, redirect_url=None)

    def confirm(self, *, params: dict, settings: dict) -> PaymentResult:
        return PaymentResult(False, params.get("order", ""), None, 0, "manual", "Pay at the office.")

    def refund(self, *, order: dict, amount_cents: int, settings: dict) -> PaymentResult:
        return PaymentResult(True, order["number"], None, amount_cents, "manual", "Refund issued by the office.")

    def terminal_charge(self, *, order: dict, terminal_id: str, settings: dict) -> PaymentResult:
        return PaymentResult(False, order["number"], None, 0, "card", "No card terminal is connected.")


register(ManualPayment())
