# Security

Open County Portal handles staff accounts, payment records and uploads that
can include ID photos. We take reports seriously.

## Reporting a vulnerability

Please report privately, not in a public issue: use GitHub's "Report a
vulnerability" (private security advisory) on this repository.

Include what you found, how to reproduce it, and what an attacker could do.
We'll acknowledge within 3 business days, keep you informed, and credit you
in the release notes unless you prefer otherwise.

Please don't test against a county's live site. Install your own copy
(`deploy/install.sh` with `internal` certificate mode) and use the sample
data.

## What happens next

1. We confirm the problem and its severity.
2. We prepare a fix privately and release it as a patch version.
3. We publish a security advisory saying what was affected, which versions,
   and what administrators should do (usually `sudo countyctl update`).

## Supported versions

The latest minor release receives security fixes. Administrators should keep
up to date with `countyctl update`; updates take a backup and roll back on
their own if anything fails.

## Design notes

- Card data never reaches the portal; processors' hosted pages and terminals
  handle it.
- Staff sign-in requires a password (Argon2-hashed) and a TOTP code;
  accounts lock after repeated failures; sessions end after 60 idle minutes.
- Every staff action is in the audit log.
- Public pages send a strict Content-Security-Policy; forms use CSRF tokens.
- Restricted documents and redacted content never reach public pages, the
  API, or bulk files.
