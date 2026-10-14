"""Template for a real processor adapter. NOT registered.

Copy this file to <processor>.py, implement each method against your
processor's documented hosted-payment API, add an import line at the bottom
of payments/__init__.py, and add the processor's settings to the staff
console's Payments page (they are stored in settings 'payments'.
'processor_settings' and never shown back in full).

Rules every adapter must follow:
  1. Card data is entered only on the processor's hosted page or terminal.
     Never accept a card number in a portal form.
  2. Verify every response from the processor (signature, HMAC or an API
     lookup by reference). Never trust query-string values alone.
  3. Pass per-office splits if the processor supports split settlement, so
     each elected office's merchant account receives its own share.
  4. Make confirm() idempotent: the resident may reload the return page.
  5. Raise no exceptions for ordinary declines; return ok=False with a plain
     message a resident can act on.
"""
from __future__ import annotations

from . import PaymentResult, SplitLine, StartResult


class ExampleProcessor:
    code = "example"
    name = "Example processor"
    is_test = False
    supports_online = True
    supports_terminal = False

    def start(self, *, order: dict, splits: list[SplitLine], return_url: str, cancel_url: str,
              settings: dict) -> StartResult:
        # 1. Call the processor's "create hosted payment session" endpoint with
        #    order["total_cents"], order["number"], return_url and cancel_url,
        #    using credentials from settings (e.g. settings["api_key"]).
        # 2. Return the hosted page address the processor gives back.
        raise NotImplementedError("Implement start() for your processor.")

    def confirm(self, *, params: dict, settings: dict) -> PaymentResult:
        # Verify the processor's signature or look the session up by reference,
        # then report the outcome.
        raise NotImplementedError("Implement confirm() for your processor.")

    def refund(self, *, order: dict, amount_cents: int, settings: dict) -> PaymentResult:
        raise NotImplementedError("Implement refund() for your processor.")

    def terminal_charge(self, *, order: dict, terminal_id: str, settings: dict) -> PaymentResult:
        raise NotImplementedError("This processor has no terminal integration.")
