# Open County Portal

Free, open-source, self-hosted government website software for counties,
cities and special districts: county clerk official records search (deeds,
liens and plats, with free uncertified copies), online payments for property
tax, court costs, utility bills and fees (Stripe Checkout or pay at the
office), a counter point of sale, meetings and agendas, public notices, and a
free open API with a DCAT-US `data.json` open data catalog that Data.gov
harvests. Licensed under the GNU AGPL.

**Accessibility and freedom:** every page meets WCAG 2.1 AA, the standard the
ADA Title II rule sets for state and local government websites, and works on
any phone, with or without JavaScript. Every piece of public data is free to
use through the API, daily bulk files, and the DCAT-US catalog. No license
fees, no lock-in, no vendor holding your data.

## A few terms

- **`countyctl`**: the administrator's command on the server (status, backup, restore, update).
- **State pack**: a bundle that sets up one state's offices, fees, required postings and records rules.
- **DCAT-US**: the catalog format Data.gov reads, so your open data is listed there automatically.
- **Change feed**: an API endpoint that lists what changed since a given time, for anyone keeping a copy of the data.

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

## Run it locally with Docker in three commands

You need Docker (Docker Engine on Linux, Docker Desktop on Mac or Windows with
WSL) and access to hub.docker.com. Then:

```
git clone https://github.com/OSGovt/open-county-portal.git
cd open-county-portal
./deploy/local/start.sh
```

The first run builds the portal (5 to 10 minutes) and generates the fictional
Utopia County. Open http://localhost:8080, search records for `smith`, and
sign in to the staff console with the email and temporary password the script
prints. Details, Windows steps and how to erase it:
[Demonstration site](docs/admin/hosted-demo.md).

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

Install on a fresh Ubuntu 24.04 server (pinned to the current release; see
[Updates](docs/admin/updates.md) for moving between versions):

```
sudo apt-get install -y git && sudo git clone --branch v1.0.0 https://github.com/OSGovt/open-county-portal.git /opt/county-portal && cd /opt/county-portal && sudo ./deploy/install.sh
```

Or try the fictional Utopia County with 200,000 generated records on your own
computer, or publish that demonstration (demo only, not a real installation)
on Cloudflare: [Demonstration site](docs/admin/hosted-demo.md).

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
