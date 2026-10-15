# Conformance suite

Checks a running portal against what Open County Portal promises: accessibility,
working without JavaScript, the open API, bulk files, the Data.gov catalogs and
basic security headers. Run it before go-live, after every update, and whenever
you change the theme or add content templates.

It reads public pages and submits public forms empty to check error handling.
Empty submissions are rejected by the portal, so nothing is created.

## Run it

Run it from a computer that can reach the portal: a workstation or a spare
Linux machine is best, so the browser it uses isn't installed on the live
server. These steps are for Ubuntu (on Windows, use WSL with Ubuntu).

1. Install the tools and get a copy of the project (use the same release as
   your portal):

```
sudo apt-get install -y git python3-venv nodejs npm
```

```
git clone --branch v1.0.0 https://github.com/OSGovt/open-county-portal.git && cd open-county-portal/conformance
```

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```
sudo .venv/bin/playwright install-deps chromium && .venv/bin/playwright install chromium && npm ci
```

2. Run the checks (from the `conformance` folder):

```
.venv/bin/python run.py --url https://portal.example-county.gov
```

3. Open the report it names (in `conformance/reports/`). Failures are listed first,
   each with what to fix.

Options:

| Option | What it does |
|---|---|
| `--only api,catalog` | Run only some areas: `accessibility`, `no-js`, `api`, `bulk`, `catalog`, `security` |
| `--max-pages 80` | Check more pages for accessibility (default 40) |
| `--no-forms` | Don't submit forms |
| `--no-link-check` | Don't download every file listed in the catalog |
| `--insecure` | Accept an untrusted certificate (test servers in `internal` mode) |

## What it can and can't tell you

Automated accessibility checks find only part of the problems real people hit.
A clean run means no known machine-detectable failures; it doesn't mean the site
conforms to WCAG 2.1 AA. Finish with the manual review in
[docs/admin/accessibility-testing.md](../docs/admin/accessibility-testing.md).

The catalog checks cover the fields Data.gov requires. For the official answer,
paste your `/data.json` address into the Data.gov validator at
https://harvest.data.gov/validate/.

## Results

| Result | Meaning |
|---|---|
| PASS | Checked and fine |
| WARN | Worth fixing, but not a WCAG 2.1 AA failure or a Data.gov requirement |
| FAIL | Must be fixed before go-live |
| SKIP | Couldn't be checked here; the line says why |

The exit code is 1 when anything failed, so it can run in a scheduled job or CI.
