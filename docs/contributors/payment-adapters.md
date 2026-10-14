# Writing a payment adapter

An adapter connects the portal to one payment processor. Counties use many
different processors, often chosen years ago for in-person cards, so adding
adapters is one of the most useful contributions an implementer can make.
A typical adapter is 100 to 200 lines.

The portal never handles card numbers. An adapter sends the resident to the
processor's hosted payment page (or starts a charge on a processor terminal
at the counter) and then verifies the result with the processor.

## The interface

`portal/payments/__init__.py` defines it:

```python
class Adapter(Protocol):
    code: str               # short id stored on orders, e.g. "stripe"
    name: str               # shown in Settings
    is_test: bool           # True only for the built-in test processor
    supports_online: bool
    supports_terminal: bool

    def start(self, *, order, splits, return_url, cancel_url, settings) -> StartResult: ...
    def confirm(self, *, params, settings) -> PaymentResult: ...
    def refund(self, *, order, amount_cents, settings) -> PaymentResult: ...
    def terminal_charge(self, *, order, terminal_id, settings) -> PaymentResult: ...
```

- `order` is a dict with at least `number`, `total_cents`, `email`,
  `processor_ref` (after payment), and `lines`.
- `splits` is a list of `SplitLine(office_slug, merchant_account, amount_cents)`,
  one per office in the order, using the merchant accounts entered in
  Settings. Pass them to the processor if it supports split settlement.
- `settings` is the dict an administrator entered as "Processor settings"
  (`name: value` lines), such as API keys. It's stored in the database and
  never shown back in full.

### `start`

Create a payment session with the processor for `order["total_cents"]`, with
`order["number"]` as the reference, and return
`StartResult(redirect_url=...)`. The portal sends the resident there.
`return_url` is `https://<site>/checkout/return/<code>`; append whatever query
parameters your processor needs to identify the session on return.

### `confirm`

Called when the resident comes back to `return_url`, with the query
parameters as `params`. **Never trust the query string.** Verify with the
processor: look the session up by its id through the processor's API, or
check an HMAC signature with a secret only you and the processor share.
Return a `PaymentResult` with the order number taken from the verified
response, the amount the processor actually charged, and the processor's
payment reference (it's stored as `processor_ref` and used for refunds).

The portal then checks that the amount is at least the order total, and marks
the order paid. Marking paid is idempotent, so a resident reloading the
return page is harmless.

### `refund`

Refund `amount_cents` of the payment identified by `order["processor_ref"]`.
Called when a supervisor voids a paid order. Return `ok=False` with a plain
message if the processor refuses; the order is then not voided.

### `terminal_charge`

For processors with a counter terminal integration: start a charge on
`terminal_id` and wait for the result. Return `ok=False` with a message if
unsupported.

## Rules

1. Card data is entered only on the processor's page or terminal. Never add a
   card number field to a portal form.
2. Verify every response with the processor.
3. Use the processor's idempotency mechanism (often an `Idempotency-Key`
   header keyed by order number) so retries never double-charge.
4. Ordinary declines are not exceptions: return `ok=False` with a message a
   resident can act on ("The card was declined. No charge was made.").
   Raise only for configuration problems, with a message an administrator can
   act on ("The API key is missing; add it under Processor settings.").
5. Bank payments (ACH) that settle days later need the processor's webhook
   to finalize. Don't report them paid on return unless the processor says
   the funds are captured.

## Steps

1. Copy the template:

```
cp portal/payments/example_adapter.py portal/payments/myprocessor.py
```

2. Implement the four methods against the processor's documented hosted
   payment API. `portal/payments/stripe_checkout.py` is a complete real
   example: session creation, server-side verification on return, refunds,
   idempotency keys, and clear messages.

3. Register it: add `register(MyProcessor())` at the bottom of your file, and
   add your module to the import line at the bottom of
   `portal/payments/__init__.py`.

4. Test it without the network, against a mocked processor API, the way
   `tests/test_stripe.py` does with `httpx.MockTransport`: a successful
   payment, a decline, a forged return, a refund, and missing settings.

5. Test it for real against the processor's sandbox: a payment, a decline,
   a refund through a void, and a resident reloading the return page.

6. Document it: add a section to [Connecting a payment processor](../admin/payments.md)
   with the exact steps an administrator follows (where to get the key, which
   permissions it needs, what to enter in Processor settings), and its limits.

7. Open a pull request. Say which sandbox tests you ran, and whether any
   county runs it in production.
