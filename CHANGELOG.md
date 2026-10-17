# Changelog

Every release lists what changed for residents, for staff, and for the
administrator, plus anything an administrator must do. `countyctl update`
points here after every update.

Versions follow [Semantic Versioning](https://semver.org): 1.x updates never
require manual steps; a 2.0 would say exactly what to do, in order.

## 1.0.0

First release.

- Public site: services, offices, meetings and agendas, public notices with posting-deadline checks, alerts, search, forms with accessible error handling, and records search with free uncertified copies.
- Payments: online cart and checkout through payment-processor adapters (Stripe Checkout, pay-at-office, and a test processor for training), counter point of sale with drawers, close-out and supervisor voids that refund through the processor, finance reports and exports.
- Records: page images with redaction applied at display time, certified copies with public verification codes, machine-read text (read again from the redacted image for redacted pages), and a Social Security number scan for review.
- Open data: free open API at /api/v1, daily bulk files, change feed, and a DCAT-US catalog at /data.json for Data.gov.
- Staff console with two-step sign-in, roles, theme editor with contrast checking, content editing, request queues, go-live checklist and audit log.
- Migration toolkit for records, bills and the old website, with undo for every import.
- Installer and `countyctl` for status, health checks, backups with off-site copies, restore, and updates with automatic rollback.
- Conformance suite for accessibility, the API contract, bulk files and the Data.gov catalogs.
- A Source code page on every installation (AGPL section 13).
- Demonstration county generator (`countyctl app demo --scale`), a fictional state pack, subfolder hosting (`PORTAL_BASE_PATH`), and managed-hosting support (Render blueprint, first-start bootstrap, in-app nightly jobs), and a self-resetting public demonstration on Cloudflare Containers with a shared demo staff account (PORTAL_DEMO_MODE), deployed by GitHub Actions after CI passes, and checked after every deploy and nightly by a browser walk-through and the conformance suite.
- Project contacts at osgovt.com (MAINTAINERS.md) for security, accessibility and conduct reports.
- Documentation for administrators, officials, staff, implementers, data users, state pack authors and contributors, also built into the staff console.
- Installer writes the bulk open-data files at install time, so the catalog's download links work from the first minute.
- Install check: an unattended clean-machine install, `countyctl doctor` and the conformance suite run on GitHub on every version tag and weekly; a source archive is attached to every release automatically.
- Field notes (docs/field-notes) and a nightly traffic log, written by the project's maintenance pipeline.
