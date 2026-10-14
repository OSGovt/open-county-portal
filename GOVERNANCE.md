# Governance

## Purpose

Open County Portal exists so that every county, city and special district in
the United States can have an accessible public website, take payments
online, and publish its public data freely, without license fees or vendor
lock-in. Decisions are made in service of that purpose: residents first, then
the staff and administrators who serve them.

## Roles

- **Users:** anyone running or using the portal. Their reports set priorities.
- **Contributors:** anyone whose contribution has been accepted.
- **Maintainers:** contributors with merge rights, responsible for reviews,
  releases and security response. Listed in `MAINTAINERS.md` once the project
  has more than one.
- **State pack maintainers:** responsible for one state's pack, ideally people
  with that state's county-law expertise.

## Decisions

Most decisions happen in pull request review. A maintainer may merge after
CI passes and one approving review (two for anything touching payments,
authentication, redaction, backups or updates).

Larger changes (a new dependency, a schema change, a change to the API, a
change to what administrators must do) are proposed in an issue and left open
for at least seven days for comment before work is merged.

When maintainers disagree, they seek consensus. If that fails, a majority of
maintainers decides. The reasoning is recorded in the issue.

## Commitments that don't change by vote

- The software stays under the GNU AGPL v3.0 or later.
- The public API and bulk data stay free to use without a key.
- Accessibility to WCAG 2.1 AA (or a later standard the law adopts) is
  required for every release.
- Releases never take away a county's ability to run the portal without the
  project or any company.

## Becoming a maintainer

Contributors with a record of good reviews and contributions over several
months may be invited by the existing maintainers. Implementers are welcome,
and maintainers declare any commercial interest in a decision.

## Changes to this document

Proposed by pull request, open for comment for at least fourteen days, and
approved by a majority of maintainers.
