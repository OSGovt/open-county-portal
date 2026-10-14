# Architecture

## Shape

One server, three containers, managed by Docker Compose:

```
web   Caddy 2      HTTPS (Let's Encrypt, internal CA, or provided cert), compression, request size limit
app   the portal   FastAPI + Jinja templates + SQLAlchemy Core, served by Uvicorn workers
db    PostgreSQL 16
```

Persistent state lives on the host under `/var/lib/county-portal`
(`postgres/`, `data/`, `caddy/`, `import/`), never inside a container, so a
container can be replaced at any time. The program and `.env` live in
`/opt/county-portal`. The host-side `countyctl` script drives everything; the
web application never controls the server. It reads small status files that
`countyctl` writes in `data/status/`.

The application is deliberately simple: server-rendered HTML, SQLAlchemy Core
(no ORM sessions), no background worker process. Work that takes time runs as
`countyctl app` commands from systemd timers (the nightly job) or from an
administrator's shell.

## Requests

- **Public pages** (`routes/public.py`, `records.py`, `meetings.py`,
  `apply.py`, `pay.py`) render templates. Forms post back with a CSRF token
  stored in the signed session cookie. No JavaScript is required.
- **The staff console** (`routes/staff/`) requires a signed-in session with
  TOTP. Each route checks roles with `auth.require(request, conn, roles...)`.
  Staff sessions end after 60 idle minutes.
- **The API** (`routes/api.py`) is read-only JSON under `/api/v1`, with an
  OpenAPI document at `/api/v1/openapi.json`, CORS open to all origins, and a
  per-address rate limit (higher with a free, verified key). It returns only
  public data: `records.get(..., include_restricted=False)` is the single path
  to instruments, and it substitutes redaction-safe page text.
- **Catalogs**: `/data.json` (DCAT-US 3.0) and `/data-v1.1.json`.

Security headers are set in `app.py`: a strict Content-Security-Policy on
HTML pages (scripts only from the site itself), `X-Frame-Options: DENY`,
`nosniff`, a referrer policy, and HSTS when cookies are secure.

## Data

- **Settings** (`settings` table, `config_store.py`): site identity, theme,
  payment policy, open data terms, alert banner. Every write is copied to
  `setting_history`, so any version can be restored.
- **Records**: `instruments`, `parties` (normalized names for search, with a
  trigram index), `images` (one row per page: file, frame, checksum, OCR text
  of the original, OCR text of the redacted rendering), `redaction_marks`
  (boxes in thousandths of width and height). Redaction is applied when a page
  is rendered; originals are never modified. Rendered pages are cached by a
  key that includes the marks.
- **Money**: `fees` (versioned by effective date, with the adopting order and
  confirmation), `receivables` (bills), `orders`, `order_lines`, `tenders`,
  `drawers` and `drawer_sessions`, `escrow_accounts` and `escrow_ledger`.
  Amounts are integer cents.
- **Imports**: `import_batches`. Every imported row carries its batch
  number, so a batch can be verified, signed off, or undone as a whole.
- **Audit**: `audit_log` records who did what, when, from where.
- **Deletions** of public objects leave `tombstones`, so the change feed can
  tell API users what disappeared.

## Payments

See [payment-adapters.md](payment-adapters.md). Orders are created before
payment; a processor's verified confirmation marks them paid (idempotently);
a void reverses bill balances and escrow, and refunds through the processor
first when the payment went through one.

## Files

`data/images` holds record images exactly as imported. `data/files` holds
documents attached to pages and certified copy PDFs. `data/uploads` holds
resident uploads (ID photos are deleted after the retention period).
`data/bulk` holds dated bulk exports with `latest` pointing at the newest.
`data/cache` can be deleted at any time.

## Backups

`pg_dump -Fc` of the database plus a snapshot of `images`, `files` and
`uploads` in which unchanged files are hard links to the previous snapshot.
A manifest records checksums; `verify` checks them and that `pg_restore` can
read the dump. Off-site copying runs on the host with the administrator's
command.

## Updates

`countyctl update`: check the host, labeled backup, save a copy of the
current program, fetch the release (git tag or a release file), tag the
current image as `previous`, build, start, health check. On failure it
restores the program, the previous image and the pre-update backup. Schema
changes run at start as numbered steps (`portal/db.py`).

## Why these choices

- **Server-rendered HTML** works on any browser, with assistive technology,
  and on slow connections, and is easier to make accessible than a
  single-page application.
- **PostgreSQL** is free, reliable for decades, and handles name search over
  millions of records with a trigram index.
- **Docker Compose on one server** is something a network administrator can
  understand completely. Counties that want more (a separate database server,
  high availability) can build on the same containers.
- **Caddy** removes certificate renewal as a failure point.
