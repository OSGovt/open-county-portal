# Open County Portal

A complete, accessible public website for counties, cities and special
districts, with online payments, a counter point of sale, records search, and
a free open API for all public data. Free and open-source, under the GNU AGPL.

**Accessibility and freedom:** every page meets WCAG 2.1 AA and works on any
phone, with or without JavaScript. Every piece of public data is free to use
through the API, daily bulk files, and a DCAT-US catalog that Data.gov
harvests. No license fees, no lock-in, no vendor holding your data.

## What it does

**For residents**
- Services, offices, hours and contacts, written in plain language
- Meetings, agendas and minutes; public notices
- Property records search, page images, and free uncertified copies
- Certified copies with a verification code anyone can check online
- Pay property tax, court costs, utility bills and fees, in full or in part
- Online forms (permits, licenses, jury responses) and public information requests
- Redaction requests and accessible-version requests for records

**For staff**
- A staff console with two-step sign-in and roles
- Counter point of sale: drawers, cash, check, card, escrow, close-out, supervisor voids
- Finance reports and exports for the general ledger and billing systems
- Records administration: index corrections, restriction, redaction drawn on the page, a Social Security number scan
- Content editing, required-postings tracking, a go-live checklist, an audit log

**For administrators**
- A one-command installer and a `countyctl` command for status, health checks,
  backups, restore, and updates that undo themselves if anything fails
- A migration toolkit for records, bills and the old website, with dry runs,
  verification, sign-off and undo
- A theme editor that won't publish colors that fail contrast
- State packs that set up a state's offices, services, fees, required postings
  and records rules (Texas included; more welcome)

**For everyone**
- Open API at `/api/v1` (OpenAPI 3), bulk files, a change feed, and DCAT-US 3.0 and 1.1 catalogs
- A conformance suite that checks any running portal for accessibility, API
  contract and catalog problems

## Get started

| You are | Read |
|---|---|
| Installing it | [Administrator guide](docs/admin/README.md) |
| Deciding whether to use it | [For officials](docs/officials/README.md) |
| Using it at work | [Staff guide](docs/staff/README.md) |
| Installing it for others | [Implementer guide](docs/implementers/README.md) |
| Using the data | [Open data guide](docs/data/README.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

All documentation: [docs/](docs/README.md).

Install on a fresh Ubuntu 24.04 server:

```
sudo apt-get install -y git && sudo git clone --branch v1.0.0 https://github.com/OWNER/open-county-portal.git /opt/county-portal && cd /opt/county-portal && sudo ./deploy/install.sh
```

## How it's built

Python (FastAPI, server-rendered Jinja templates, SQLAlchemy Core),
PostgreSQL 16, and Caddy for automatic HTTPS, in three Docker containers on
one server. See [Architecture](docs/contributors/architecture.md).

## Status

Version 1.0.0. The Texas state pack is a draft pending legal review. The
Stripe Checkout adapter is tested against a simulated Stripe API; other
processors need an adapter
([how to write one](docs/contributors/payment-adapters.md)).

## License

[GNU Affero General Public License v3.0 or later](LICENSE). You may use,
study, change and share it. If you run a changed version for the public, you
must offer your changes too; every installation does this automatically with
a **Source code** link in the footer.
