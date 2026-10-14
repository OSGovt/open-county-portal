# Changelog

Every release lists what changed for residents, for staff, and for the
administrator, plus anything an administrator must do. `countyctl update`
points here after every update.

Versions follow [Semantic Versioning](https://semver.org): 1.x updates never
require manual steps; a 2.0 would say exactly what to do, in order.

## 1.0.0

First release.

- Public site: services, offices, meetings and agendas, public notices with posting-deadline checks, alerts, search, forms with accessible error handling, and records search with free uncertified copies.
- Payments: online cart and checkout through a payment-processor adapter (test processor and pay-at-office included), counter point of sale with drawers, close-out and supervisor voids, finance reports and exports.
- Records: page images with redaction applied at display time, certified copies with public verification codes, OCR text.
- Open data: free open API at /api/v1, daily bulk files, change feed, and a DCAT-US catalog at /data.json for Data.gov.
- Staff console with two-step sign-in, roles, theme editor with contrast checking, content editing, request queues, go-live checklist and audit log.
- Migration toolkit for records, bills and the old website, with undo for every import.
- Installer and `countyctl` for status, health checks, backups, restore, updates with automatic rollback.
