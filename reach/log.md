# Reach log

One entry per maintenance pass: the question targeted, the measurement
before, what changed, and the commit. Newest first. Entries are short;
the data is in the CSV files beside this file.

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
