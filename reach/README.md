# Reach data

Weekly measurements of where this project can be found, written by
`tools/reach_check.py` from `.github/workflows/reach-check.yml` (Sundays).
The objective they serve is in [`REACH.md`](../REACH.md) at the repository
root. Rows are appended; a re-run on the same day replaces that day's rows.

| File | What it holds | Source |
|---|---|---|
| `latest.md` | This week's summary, rewritten each run | all of the below |
| `github.csv` | 14-day views, unique visitors, clones, stars, top referrers and paths | GitHub traffic API (the nightly `docs/traffic/traffic.csv` keeps the daily series) |
| `agents.csv` | For each site and crawler, whether `robots.txt` lets it read the home page; status of `robots.txt`, `sitemap.xml`, `llms.txt` | the sites themselves |
| `search-console.csv` | Clicks, impressions, CTR, position per query and page, trailing 28 days | Google Search Console API (needs the `GSC_SERVICE_ACCOUNT_JSON` repository secret) |
| `bing.csv` | Clicks, impressions, average position per query, Bing's weekly buckets | Bing Webmaster Tools API (needs the `BING_WEBMASTER_API_KEY` repository secret) |
| `log.md` | What the weekly maintenance pass changed, with the measurement before it | the maintenance pass |
| `submissions/` | Drafts for third-party listings, awaiting a human yes | the maintenance pass |

Unique visitors, impressions and clicks are the numbers that mean people.
Clones are mostly CI and indexers. Nothing in here identifies a visitor.

## Connecting the two search consoles (one-time, by a maintainer)

**Google Search Console.** Verify `utopia.osgovt.com` (and `osgovt.com` once
it serves a site) as a Domain property (DNS TXT record in Cloudflare). In
Google Cloud, enable the Search Console API and create a service account with
a JSON key. In Search Console, Settings > Users and permissions > Add user:
the service account's email, Full permission. Put the JSON key's contents in
the repository secret `GSC_SERVICE_ACCOUNT_JSON`.

**Bing Webmaster Tools.** Add the same sites (Bing can import them from
Search Console). Settings > API access > generate a key, one per account. Put
it in the repository secret `BING_WEBMASTER_API_KEY`. The key can also submit
URLs and change settings, so it lives only in the secret.

Until the secrets exist, those two sections of `latest.md` say "not
connected" and the rest still runs.
