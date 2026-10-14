# Connecting a payment processor

Residents can pay property tax, court costs, utility bills, copy fees and
permit fees online, and cashiers take payments at the counter. The portal
never sees or stores a card number: online, residents type their card on the
processor's own payment page; at the counter, on the processor's terminal.

## The choices that come built in

Pick one in **Settings > Payments, records and open data > Payment
processor**.

| Choice | What happens | When to use it |
|---|---|---|
| **Test processor** | A practice payment page marked TEST. No money moves. Card `4242 4242 4242 4242` is approved; `4000 0000 0000 0002` is declined | Training and acceptance testing. The console shows a warning on every page while it's on |
| **Pay at the office or by mail** | Residents build an order online and get an order number; they pay at the counter or by mail, and the cashier marks it paid | Before you have a processor contract, or if you don't take cards online |
| **Stripe Checkout** | Residents pay on Stripe's hosted page with a card, Apple Pay or Google Pay | If your county contracts with Stripe |

Any other processor (the one your county already uses for in-person cards,
say) needs a small adapter written for it. An implementer or contributor can
build one by following
[Writing a payment adapter](../contributors/payment-adapters.md). Ask your
processor for its "hosted payment page" or "hosted checkout" documentation;
that's what the adapter uses.

## Before you connect a real processor

- **Contract and procurement.** Your purchasing rules apply to the processor
  contract. The portal itself costs nothing.
- **Fees.** Many states let a county charge a processing or convenience fee
  for card payments, with conditions. Your state pack lists the law if it's
  known (for Texas, Local Government Code 132.002 and 132.003). Your governing
  body usually has to adopt the fee. Have the county attorney confirm before
  turning a fee on.
- **Where the money goes.** Each elected office often has its own bank
  account. Enter each office's merchant or account identifier under
  **Merchant accounts**; the finance reports split every order by office so
  each office can post its share.
- **PCI DSS.** Because card details are entered only on the processor's page
  or terminal, merchants in this setup usually qualify for the shortest PCI
  self-assessment (SAQ A for online payments). Confirm with your processor or
  bank; they decide which form you file.

## Set up Stripe

1. **Create or use the county's Stripe account** (not a personal one) and
   complete its business verification.

2. **Make a restricted key.** In the Stripe Dashboard, under Developers > API
   keys, create a restricted key with write access to Checkout Sessions and
   Refunds. Start in test mode: the key begins `rk_test_`. (A standard secret
   key, `sk_test_...`, also works.) If a test payment later fails with a
   Stripe permission message, add the permission it names to the key.

3. **Turn on the payment methods** you want in the Stripe Dashboard (cards,
   Apple Pay, Google Pay). The Stripe adapter doesn't support bank-account
   (ACH) payments, because those settle days later; the portal turns the
   eCheck option off if you choose Stripe.

4. **Enter it in the portal.** **Settings > Payments, records and open
   data**:
   - Processor: **Stripe Checkout**
   - Ways residents can pay online: **Credit and debit cards** and, if turned
     on in Stripe, **Apple Pay and Google Pay**
   - Processor settings:

```
secret_key: rk_test_your_key_here
```

   Save. The key is stored in the portal's database and is never shown back
   in full.

5. **Test it.** Open the public site in a private browser window, add a bill
   or fee to the cart, and pay with Stripe's test card `4242 4242 4242 4242`
   (any future expiry date, any 3-digit code, any ZIP). You should land on the
   portal's receipt page. The payment appears in the Stripe Dashboard (test
   mode) and in **Finance** in the portal.

6. **Test a refund.** Signed in as a supervisor, go to **Counter**, then
   **Close drawer** (the Void a sale form is on that page even without an open
   drawer), enter the order number and a reason, and void it. The message should say "voided and refunded to the card". The
   refund appears in Stripe.

7. **Go live.** Make a live restricted key (`rk_live_...`) the same way,
   replace the key in Processor settings, and save. Do one real small
   payment and refund it.

**Undo:** switch the processor back to **Pay at the office or by mail** and
save. Orders already paid are unaffected.

## Processing fees

In the same settings page:

| Field | Example |
|---|---|
| Card fee, percent | `2.5` |
| Card fee, flat amount | `0.00` |
| Card fee, minimum | `2.00` |
| eCheck fee, flat amount | `1.00` |
| Authority for the fee | The order or statute residents see at checkout, such as "Processing fee set by Commissioners Court Order 2026-14 under Local Government Code 132.003" |

Residents see the fee, its authority, and the total before they pay. Leave
the fees at zero if your county absorbs them.

## The counter

Cashiers use **Counter** in the staff console.

1. A cashier opens a drawer with the starting cash.
2. For each customer: look up a bill or a fee, or open **Saved online
   orders** for an order a resident made online; add items; take cash,
   check, card, or escrow.
3. Print the receipt (Ctrl+P on the receipt page).
4. At the end of the shift, **Close drawer**: count the cash. The portal
   shows the expected amount and any difference.

**Card payments at the counter.** If your processor's terminal isn't
connected through an adapter, run the card on the terminal as you do today,
then record the payment as **card** in the counter. A supervisor voiding that
sale refunds the card on the same terminal.

**Voids** are for supervisors, with a reason. If the order was paid through
a connected processor, the void refunds it there first; if the refund fails,
nothing is voided and the message says why.

**Escrow accounts** (title companies and attorneys who prepay for copies and
recording) are set up in **Finance > Escrow accounts**.

## Finance

**Finance** shows totals by office and fund, by payment type, and by drawer,
for any date range. Downloads:

- **Download ledger (CSV)**: every payment line, for the general ledger
- **Download bill payments to post (CSV)**: bill payments to load back into
  the tax, court or utility system (see [Moving your records](migration.md#post-payments-back-to-the-billing-system))

## Check

- A test payment and refund both work end to end.
- **Finance** totals for the test day match the processor's report.
- The go-live checklist shows the processor is not the test processor.

Next: [Accessibility testing](accessibility-testing.md).
