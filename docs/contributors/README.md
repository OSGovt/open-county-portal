# Contributing code

Thank you. Every improvement here reaches every county and district that runs
the portal. Read [CONTRIBUTING.md](../../CONTRIBUTING.md) first for how
proposals and reviews work; this page is the technical part.

## What matters most

1. **The person at the other end.** A resident on an old phone with a screen
   reader, or a clerk with fifteen minutes of training. Plain language, no
   jargon, nothing that only works with a mouse.
2. **Accessibility is a requirement, not a feature.** WCAG 2.1 AA on every
   page, checked automatically in CI and by hand for new interactions.
3. **Works without JavaScript.** Every public page is rendered on the server
   and every public form is a plain HTML form. JavaScript may enhance, never
   be required. Staff pages follow the same rule except where noted (the
   redaction drawing tool, the session timeout warning).
4. **No fear of change.** Anything that changes data can be undone or comes
   with a backup. Imports are batches. Settings keep history. Updates roll
   back on their own.
5. **Open data by default.** If it's public on the website, it's in the API
   and the bulk files, free and without a key.
6. **Boring technology.** One server, PostgreSQL, server-rendered pages, few
   dependencies, all pinned. A county should be able to run this for ten years
   with one part-time administrator.

## Set up a development copy

You need Python 3.12 or newer, PostgreSQL 16 and Node.js 22 (only for the conformance
suite). On Ubuntu 24.04:

1. Install the tools:

```
sudo apt-get update && sudo apt-get install -y python3-venv postgresql tesseract-ocr poppler-utils
```

2. Get the code and a virtual environment:

```
git clone https://github.com/OSGovt/open-county-portal.git && cd open-county-portal && python3 -m venv .venv
```

```
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt -r conformance/requirements.txt
```

3. Make sure PostgreSQL is running, then make a database you're allowed to wipe
   (if `$USER` is empty, as in some containers, use `whoami` instead):

```
sudo service postgresql start
```

```
sudo -u postgres createuser -s "$(whoami)" && createdb portal_dev && createdb portal_test
```

4. Run the portal with sample data:

```
export PORTAL_ENV=development PORTAL_DATABASE_URL="postgresql+psycopg:///portal_dev" PORTAL_DATA_DIR="$PWD/.data" PORTAL_SECURE_COOKIES=false
```

```
.venv/bin/python -m portal.cli setup --name "Dev County" --type county --state tx --admin-email you@example.com && .venv/bin/python -m portal.cli demo
```

```
.venv/bin/uvicorn portal.app:create_app --factory --reload
```

Open http://localhost:8000. The staff console is at /staff; the setup
command printed the temporary password.

The development sample data is small and every record says SAMPLE. Things to
try: records search for `resident` or `homeowner` (the 200,000-record Utopia
County demo in [hosted-demo.md](../admin/hosted-demo.md) is where `smith` and
`garcia` live), the API at `/api/v1/instruments?name=resident`, and a property
tax lookup for account `R000123` or `R000456`.

## Tests

```
PORTAL_TEST_DATABASE_URL="postgresql+psycopg:///portal_test" .venv/bin/python -m pytest -q
```

The test database is wiped at the start of every run. The suite includes the
conformance suite, which starts a real server and runs axe-core in Chromium;
for that part install the browser and axe-core once:

```
.venv/bin/playwright install --with-deps chromium && (cd conformance && npm ci)
```

Without them, the accessibility checks are skipped and the rest still run.

CI (`.github/workflows/ci.yml`) runs everything on every pull request, plus
`shellcheck` on the shell scripts, validation of every state pack, and a
build and health check of the Docker image.

## Where things are

| Path | What |
|---|---|
| `portal/app.py` | Application setup, security headers, API rate limiting, error pages |
| `portal/settings.py` | Settings from environment variables |
| `portal/db.py` | Every table, and the numbered schema upgrade steps |
| `portal/web.py` | Template rendering, CSRF, flash messages, money formatting |
| `portal/auth.py` | Staff accounts, roles, passwords (Argon2), TOTP, lockout, idle timeout |
| `portal/records.py`, `images.py` | Records search, page rendering with redaction, OCR, PDFs |
| `portal/fees.py`, `cart.py`, `orders.py` | Fee schedule with effective dates, cart pricing, orders and tenders |
| `portal/payments/` | Payment adapters (see [payment-adapters.md](payment-adapters.md)) |
| `portal/theme.py` | Theme engine with contrast repair |
| `portal/statepacks/` | State packs (see [Writing a state pack](../state-packs/writing-a-state-pack.md)) |
| `portal/compliance.py` | Required postings check, ADA Title II dates |
| `portal/bulk.py` | Daily bulk files |
| `portal/ops.py`, `ops_status.py` | Backup, verify, restore; status for the dashboard |
| `portal/migrate/` | Migration toolkit: records, bills, old website |
| `portal/cli.py` | `countyctl app` commands |
| `portal/routes/` | Public pages, payments, API; `routes/staff/` for the console |
| `portal/templates/`, `static/` | Jinja templates and the one stylesheet |
| `deploy/` | Installer, `countyctl`, Caddy configurations |
| `conformance/` | The conformance suite |
| `docs/` | All documentation, also shown in the staff console's Help |

More detail: [Architecture](architecture.md).

## Changing the database

New tables are created automatically. Any change to an existing table is a
numbered step in `MIGRATIONS` in `portal/db.py`: raise `SCHEMA_VERSION` by
one and add the SQL. Steps must be safe to run twice (`IF NOT EXISTS`) and
must never delete residents' data. `countyctl update` backs up before they
run and restores the backup if the new version doesn't start.

## Writing for people

Everything a resident or staff member reads: short sentences, common words,
active voice, say what to do next. "Enter the amount, like 25.00" rather than
"Invalid input". Error messages say what happened and how to fix it. Avoid
legal citations in resident-facing text except where the law requires them.

## Before you open a pull request

- [ ] Tests pass, and new behavior has a test
- [ ] New pages pass the conformance suite
- [ ] Works without JavaScript
- [ ] Any schema change is a numbered upgrade step
- [ ] Documentation updated: the admin guide if an administrator does
      anything differently, the changelog for everything
- [ ] No new dependency unless it's well maintained, pinned, and clearly
      worth the maintenance cost
