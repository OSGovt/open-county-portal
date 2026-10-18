# Reach log

One entry per maintenance pass: the question targeted, the measurement
before, what changed, and the commit. Newest first. Entries are short;
the data is in the CSV files beside this file.

## 2026-10-18 — README lead in the askers' words (county-clerk and county-it personas)

- Targeted: the county-clerk and county-it cold-probe personas, and
  REACH.md questions 1, 2 and 7.
- Measurement before: web search, top ten, all eight REACH.md questions and
  the project's own name absent (`reach/probes.md`, 2026-10-18). Cold probe
  2026-10-17 (`reach/cold.csv`): five personas, 35 searches, found in 0
  results and 0 answers; recommended instead: tylertech.com,
  github.com/mayan-edms, publicsearch.us (clerk); edmundsgovtech.com,
  centralsquare.com (IT); munibit.com, townweb.com (district); drupal.org,
  dkan, councilmatic.org (implementer); docs.ckan.org, getdkan.org
  (open-data). GitHub, 14 days: 2 unique visitors, 29 views, 133 unique
  cloners, 0 stars; sole referrer github.com (`reach/github.csv`).
- Changed: `README.md` first paragraph and the install heading now use the
  words the probed assistants searched with (`reach/harvest.csv`): county
  clerk official records search, deeds, liens and plats, self-hosted,
  property tax and utility bill online payments, Stripe Checkout, meetings and
  agendas, DCAT-US `data.json`, ADA Title II, Docker. Each claim traces to
  `docs/admin/payments.md`, `docs/data/README.md`, `docs/admin/migration.md`
  or `ACCESSIBILITY.md`. Commit 1258054 (OSGovt/open-county-portal).
- Needs a human: the repository description and topics could not be changed
  from the maintenance pass (GitHub settings writes are refused through its
  proxy). Proposed description (330 characters): "Free, open-source,
  self-hosted website software for counties, cities and special districts:
  county clerk official records search (deeds, liens, plats), online
  payments for property tax, court costs and utility bills, counter point of
  sale, meetings and agendas, DCAT-US data.json open data catalog for
  Data.gov. WCAG 2.1 AA. AGPL." Proposed added topics: self-hosted,
  county-clerk, records-search, property-tax, dcat-us, data-gov,
  special-districts (20 total with the existing 13).
- Not changed: OSGovt.com pages (repository not reachable from this pass);
  `reach/agents.csv` 2026-10-17 shows `osgovt.com` unreachable to the probe
  (ConnectError) and `utopia.osgovt.com` blocking ClaudeBot and GPTBot at
  the home page.

## 2026-10-16 — loop installed

- Measurement before: web search, top ten results, no project page for
  "free open source county records portal", "county website online payments
  records search open source", "WCAG accessible county website open source
  AGPL", or "OSGovt open county portal". GitHub, 14 days to today: 2 unique
  visitors, 17 views, 50 unique cloners (`docs/traffic/traffic.csv`).
  Agent access: `utopia.osgovt.com` and `oscivic.com` readable by an AI
  fetcher; `osgovt.com` root returns a robots disallow to it.
- Changed: added `REACH.md` (objective), `reach/` (data and this log),
  `tools/reach_check.py` and the weekly `reach-check.yml` workflow; the
  portal now serves `/llms.txt` so assistants can read what a site offers;
  `/source` and `/data` added to the sitemap.
- Not yet connected: Search Console and Bing Webmaster (secrets not set).
