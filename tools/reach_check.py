"""Weekly reach measurements: where can this project be found, and by whom?

Writes CSV files under reach/ (one row per measurement, appended, deduplicated)
and a short reach/latest.md summary. Sources, each skipped with a note when its
credentials are absent:

  GitHub traffic API      referrers and popular paths (14-day windows)    GH_TOKEN
  Robots / agent probe    can search engines and AI assistants read each site?  (no credentials)
  Google Search Console   clicks, impressions, position per query and page  GSC_SERVICE_ACCOUNT_JSON
  Bing Webmaster Tools    the same, in Bing's weekly buckets                BING_WEBMASTER_API_KEY

Usage:  python tools/reach_check.py OSGovt/open-county-portal reach/sites.json
Nothing here is sent anywhere except to the APIs named above, read-only.
"""
import csv
import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib import robotparser
from urllib.parse import quote

import httpx

TODAY = date.today().isoformat()
OUT = Path("reach")
UA = "OpenCountyPortal-ReachCheck/1.0 (+https://github.com/OSGovt/open-county-portal)"

# Crawlers whose access decides whether people find the site through search or an assistant.
AGENTS = ["Googlebot", "Bingbot", "DuckDuckBot", "ClaudeBot", "Claude-User", "Claude-SearchBot",
          "GPTBot", "ChatGPT-User", "OAI-SearchBot", "PerplexityBot", "Perplexity-User"]

notes = []


def append_rows(path: Path, fields: list[str], rows: list[dict], key: tuple[str, ...]) -> int:
    """Append rows to a CSV, replacing any existing row with the same key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        with path.open(newline="") as fh:
            existing = list(csv.DictReader(fh))
    new_keys = {tuple(r[k] for k in key) for r in rows}
    kept = [r for r in existing if tuple(r.get(k, "") for k in key) not in new_keys]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(kept + rows)
    return len(rows)


def gh(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def github_traffic(repo: str) -> str:
    try:
        views, clones = gh(f"repos/{repo}/traffic/views"), gh(f"repos/{repo}/traffic/clones")
        refs, paths, meta = gh(f"repos/{repo}/traffic/popular/referrers"), gh(f"repos/{repo}/traffic/popular/paths"), gh(f"repos/{repo}")
    except subprocess.CalledProcessError as exc:
        notes.append(f"GitHub traffic: skipped ({exc})"); return "GitHub traffic: not available"
    row = {"date": TODAY, "views_14d": views["count"], "unique_visitors_14d": views["uniques"],
           "clones_14d": clones["count"], "unique_cloners_14d": clones["uniques"],
           "stars": meta["stargazers_count"], "forks": meta["forks_count"], "watchers": meta["subscribers_count"],
           "referrers": json.dumps([[r["referrer"], r["count"], r["uniques"]] for r in refs[:10]]),
           "paths": json.dumps([[p["path"], p["count"], p["uniques"]] for p in paths[:10]])}
    append_rows(OUT / "github.csv", list(row), [row], ("date",))
    top = ", ".join(f"{r['referrer']} ({r['uniques']})" for r in refs[:5]) or "none"
    return (f"GitHub, last 14 days: {views['uniques']} unique visitors, {views['count']} views, "
            f"{clones['uniques']} unique cloners; {meta['stargazers_count']} stars. Referrers: {top}.")


def agent_probe(sites: list[dict]) -> str:
    rows, lines = [], []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
        for site in sites:
            base = site["url"].rstrip("/")
            status = {}
            for page in ("/robots.txt", "/sitemap.xml", "/llms.txt", "/"):
                try:
                    status[page] = client.get(base + page).status_code
                except httpx.HTTPError as exc:
                    status[page] = f"error: {type(exc).__name__}"
            rp = robotparser.RobotFileParser()
            robots_ok = status["/robots.txt"] == 200
            if robots_ok:
                rp.parse(client.get(base + "/robots.txt").text.splitlines())
            for agent in AGENTS:
                if robots_ok:
                    allowed = str(rp.can_fetch(agent, base + "/")).lower()
                elif status["/robots.txt"] == 404:
                    allowed = "true"          # no robots.txt means no restrictions
                else:
                    allowed = "unknown"       # couldn't read robots.txt this week
                rows.append({"date": TODAY, "site": base, "agent": agent, "home_allowed": allowed,
                             "robots": status["/robots.txt"], "sitemap": status["/sitemap.xml"],
                             "llms_txt": status["/llms.txt"], "home": status["/"]})
            if robots_ok:
                blocked = ", ".join(a for a in AGENTS if not rp.can_fetch(a, base + "/")) or "none"
            else:
                blocked = "unknown (robots.txt not readable)"
            lines.append(f"{base}: home {status['/']}, robots {status['/robots.txt']}, sitemap {status['/sitemap.xml']}, "
                         f"llms.txt {status['/llms.txt']}; blocked at home: {blocked}")
    append_rows(OUT / "agents.csv", list(rows[0]) if rows else ["date"], rows, ("date", "site", "agent"))
    return "Agent access:\n  " + "\n  ".join(lines)


def search_console(sites: list[dict]) -> str:
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if not raw:
        notes.append("Search Console: skipped (GSC_SERVICE_ACCOUNT_JSON not set)"); return "Search Console: not connected"
    try:
        from google.auth.transport.requests import Request  # type: ignore
        from google.oauth2 import service_account  # type: ignore
    except ImportError:
        notes.append("Search Console: skipped (google-auth not installed)"); return "Search Console: google-auth missing"
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    creds.refresh(Request())
    end = date.today() - timedelta(days=3)          # Search Console data lags about two days
    start = end - timedelta(days=27)
    rows, lines = [], []
    with httpx.Client(headers={"Authorization": f"Bearer {creds.token}"}, timeout=60) as client:
        for site in sites:
            prop = site.get("gsc_property") or site["url"].rstrip("/") + "/"
            r = client.post(f"https://www.googleapis.com/webmasters/v3/sites/{quote(prop, safe='')}/searchAnalytics/query",
                            json={"startDate": start.isoformat(), "endDate": end.isoformat(),
                                  "dimensions": ["query", "page"], "rowLimit": 500})
            if r.status_code != 200:
                lines.append(f"{prop}: HTTP {r.status_code} ({r.text[:120]})"); continue
            data = r.json().get("rows", [])
            for d in data:
                rows.append({"window_end": end.isoformat(), "property": prop, "query": d["keys"][0], "page": d["keys"][1],
                             "clicks": d["clicks"], "impressions": d["impressions"], "ctr": round(d["ctr"], 4),
                             "position": round(d["position"], 1)})
            imps = sum(d["impressions"] for d in data); clicks = sum(d["clicks"] for d in data)
            lines.append(f"{prop}: {imps} impressions, {clicks} clicks, {len(data)} query/page pairs ({start} to {end})")
    if rows:
        append_rows(OUT / "search-console.csv", list(rows[0]), rows, ("window_end", "property", "query", "page"))
    return "Search Console (28 days):\n  " + "\n  ".join(lines)


def bing(sites: list[dict]) -> str:
    key = os.environ.get("BING_WEBMASTER_API_KEY")
    if not key:
        notes.append("Bing Webmaster: skipped (BING_WEBMASTER_API_KEY not set)"); return "Bing Webmaster: not connected"
    rows, lines = [], []
    with httpx.Client(timeout=60) as client:
        for site in sites:
            prop = site.get("bing_property") or site["url"].rstrip("/") + "/"
            r = client.get("https://ssl.bing.com/webmaster/api.svc/json/GetQueryStats",
                           params={"siteUrl": prop, "apikey": key})
            if r.status_code != 200:
                lines.append(f"{prop}: HTTP {r.status_code}"); continue
            data = r.json().get("d", [])
            for d in data:
                ms = int(d["Date"].strip("/").replace("Date(", "").replace(")", "").split("+")[0].split("-")[0])
                rows.append({"bucket": time.strftime("%Y-%m-%d", time.gmtime(ms / 1000)), "property": prop,
                             "query": d["Query"], "clicks": d["Clicks"], "impressions": d["Impressions"],
                             "avg_impression_position": d["AvgImpressionPosition"],
                             "avg_click_position": d["AvgClickPosition"]})
            lines.append(f"{prop}: {sum(d['Impressions'] for d in data)} impressions over {len(data)} query rows (all time)")
    if rows:
        append_rows(OUT / "bing.csv", list(rows[0]), rows, ("bucket", "property", "query"))
    return "Bing Webmaster:\n  " + "\n  ".join(lines)


def main(repo: str, sites_file: str) -> int:
    sites = json.loads(Path(sites_file).read_text())["sites"]
    sections = [github_traffic(repo), agent_probe(sites), search_console(sites), bing(sites)]
    summary = [f"# Reach measurements, {TODAY}", "", *[s + "\n" for s in sections]]
    if notes:
        summary += ["Not measured this week:", *[f"- {n}" for n in notes]]
    (OUT / "latest.md").write_text("\n".join(summary) + "\n")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "reach/sites.json"))
