"""Payment processor adapters.

The portal never sees full card numbers. Each adapter hands the resident to
the processor's own hosted payment page (or a processor terminal at the
counter) and receives back a result. To support a new processor, copy
example_adapter.py, fill in the four methods, and register it below. See
docs/contributors/payment-adapters.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class StartResult:
    redirect_url: str | None = None   # send the resident here to pay
    completed: bool = False           # True if no redirect is needed (e.g. pay later at the office)
    processor_ref: str | None = None


@dataclass
class PaymentResult:
    ok: bool
    order_number: str
    processor_ref: str | None
    amount_cents: int
    method: str
    message: str = ""


@dataclass
class SplitLine:
    office_slug: str
    merchant_account: str | None
    amount_cents: int


class Adapter(Protocol):
    code: str
    name: str
    is_test: bool
    supports_online: bool
    supports_terminal: bool

    def start(self, *, order: dict, splits: list[SplitLine], return_url: str, cancel_url: str,
              settings: dict) -> StartResult: ...

    def confirm(self, *, params: dict, settings: dict) -> PaymentResult: ...

    def refund(self, *, order: dict, amount_cents: int, settings: dict) -> PaymentResult: ...

    def terminal_charge(self, *, order: dict, terminal_id: str, settings: dict) -> PaymentResult: ...


_registry: dict[str, Adapter] = {}


def register(adapter: Adapter) -> None:
    _registry[adapter.code] = adapter


def get(code: str) -> Adapter:
    if code not in _registry:
        raise KeyError(f"No payment adapter '{code}'. Installed: {', '.join(sorted(_registry))}.")
    return _registry[code]


def installed() -> dict[str, Adapter]:
    return dict(_registry)


from . import manual, stripe_checkout, test_processor  # noqa: E402,F401  (registers built-in adapters)
