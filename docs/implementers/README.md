# Implementer guide

There are more than 3,000 counties and about 40,000 special districts in the
United States (Census Bureau, 2025), and most can't spare a developer. This
guide is for the independent IT consultants, small firms, regional councils
of government, state associations and county IT shops who install and look
after Open County Portal for them.

The software is free, and every guide needed to run it is public, so a county
can always do it alone. What you offer is time, experience and someone to
call. That's a real service, and you may charge for it.

## Ground rules

- **The county owns everything:** the server or cloud account, the domain,
  the data, the admin accounts. Set them up in the county's name from day
  one. Hand over every password at the end.
- **Contribute back.** Fixes, payment adapters, state pack improvements and
  translations you write go to the project, so the county is never dependent
  on you for them. The license requires sharing changes to code you run for
  the public anyway.
- **No lock-in by other means either:** no private forks, no add-ons only you
  can maintain, no data held back.
- **Don't misrepresent the project.** You implement and support it; you
  don't own it. Don't call it your product.
- **Accessibility is the point.** Don't hand over a site that fails the
  conformance suite.

## A standard engagement

Every step points to the administrator guide, which is the source of truth.
You're doing what it says, with experience.

### 1. Discovery (1 to 3 meetings)

Collect:

- [ ] Government type, population, state; the state pack's status for that
      state ([state packs](../state-packs/writing-a-state-pack.md))
- [ ] Current website: who hosts it, page count, who edits it
- [ ] Records system: vendor, number of documents and pages, export formats,
      export cost and lead time (ask early; this is usually the longest wait)
- [ ] Billing systems for tax, court and utility: can they export nightly?
- [ ] Payment processor today, contract terms, whether an adapter exists
      ([payments](../admin/payments.md))
- [ ] Email relay, DNS control, firewall team, where the server will live
- [ ] Who in each office owns content, and who signs off on records
- [ ] The governing body's decisions ([for officials](../officials/README.md#decisions-for-your-governing-body-and-offices))

### 2. Statement of work

List deliverables tied to the go-live checklist, so "done" is objective:
installed, styled, records imported and signed off, bills syncing, payments
live, staff trained, conformance report clean, Data.gov submitted, cut over.
Say what's the county's job (decisions, content review, vendor exports).

### 3. Install and set up (days)

[Install](../admin/install.md), [HTTPS](../admin/https.md),
[email](../admin/email.md), [off-site backups](../admin/backups.md),
[staff accounts](../admin/staff-accounts.md), [styling](../admin/styling.md).
Use a temporary address and the test processor.

### 4. Train with sample data

Load sample data. Run one session per role using the
[staff guide](../staff/README.md): content editors, records clerks, cashiers
and supervisors, finance, public information, applications. Have each
cashier open and close a drawer.

### 5. Migrate (weeks)

[Moving your records](../admin/migration.md). Do a 100-document sample from
the records vendor first. Keep a log of mapping decisions for the county.
Get the clerk's sign-off in the console for every batch.

### 6. Test

Run the conformance suite and the manual review
([accessibility testing](../admin/accessibility-testing.md)). Test payments
end to end with the real processor's sandbox, then one small live payment and
refund. Practice a restore on a test server.

### 7. Go live

[Go-live checklist and cutover](../admin/cutover.md). Be there on the day,
and have the way back written down.

### 8. Hand over

- [ ] All passwords and the `.env` copy in the county's password manager
- [ ] The county's administrator has run `countyctl doctor`, a backup, and an
      update on a test server themselves
- [ ] A written record of mapping decisions, settings choices and anything
      unusual
- [ ] Final conformance report

## Support after go-live

Typical ongoing services: applying updates, watching backups and
certificates, answering staff questions, annual accessibility review, help
with new forms and pages, and adapting to law changes. Whatever you agree,
put in writing what happens if the agreement ends: the site keeps running and
the county's administrator can carry on with the public guides.

## Estimating

Rough guides from the work involved; your experience will refine them.

| Factor | Effect |
|---|---|
| Records vendor export | The biggest unknown. Ask on day one; lead times of weeks are common |
| Records volume | Import time grows with pages (hours per million pages, depending on server and image format); review time doesn't |
| Old website size | A few hundred pages is typical; review by offices is the slow part |
| Payment processor | Existing adapter: an hour or two. New adapter: a few days including sandbox testing |
| State pack | None for the state yet: add time to set up offices and services by hand, or write the pack and contribute it |
| Number of offices | Each office is a training session and a content review |

## Working with many counties

- Standardize: same server image, same off-site backup pattern, same
  monitoring. `countyctl doctor` exits with an error when something needs
  attention, so it's easy to run from your monitoring system over SSH.
- Run the conformance suite on a schedule against every site you support.
- Contribute your improvements; every one makes the next installation
  faster.

## Getting listed

The project may keep a list of implementers who agree to these ground
rules, with links to counties they've served. A listing is not an
endorsement, and counties should check references.
