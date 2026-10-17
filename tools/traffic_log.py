"""Append GitHub traffic numbers for this repository to docs/traffic/traffic.csv.

GitHub keeps only 14 days of traffic. Run nightly (the repair run does) to keep a
permanent record. Safe to run repeatedly: one row per day, later runs update it.

    python tools/traffic_log.py OSGovt/open-county-portal
"""
import csv, json, subprocess, sys
from datetime import date
from pathlib import Path

FIELDS = ["date", "views_14d", "unique_visitors_14d", "clones_14d", "unique_cloners_14d",
          "stars", "forks", "watchers", "top_referrer"]

def gh(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))

def main(repo, out=Path("docs/traffic/traffic.csv")):
    views, clones, meta = gh(f"repos/{repo}/traffic/views"), gh(f"repos/{repo}/traffic/clones"), gh(f"repos/{repo}")
    refs = gh(f"repos/{repo}/traffic/popular/referrers")
    row = {"date": date.today().isoformat(), "views_14d": views["count"], "unique_visitors_14d": views["uniques"],
           "clones_14d": clones["count"], "unique_cloners_14d": clones["uniques"],
           "stars": meta["stargazers_count"], "forks": meta["forks_count"], "watchers": meta["subscribers_count"],
           "top_referrer": refs[0]["referrer"] if refs else ""}
    rows = []
    if out.exists():
        with out.open(newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if r["date"] != row["date"]]
    rows.append(row)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    print(",".join(str(row[f]) for f in FIELDS))

if __name__ == "__main__":
    main(sys.argv[1])
