"""Required-postings check: compares what the state pack requires with what
is actually posted, and reports anything missing, late or stale in plain
English. Runs on the dashboard and nightly (countyctl app postings-check)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from . import config_store, statepacks
from .db import meetings, postings, utcnow


def check_postings(conn: Connection) -> list[dict]:
    site = config_store.get(conn, "site")
    try:
        rules = statepacks.posting_rules(site["state"], site["jurisdiction_type"])
    except statepacks.PackError as exc:
        return [{"code": "pack", "title": "State pack", "authority": "", "status": "bad", "detail": str(exc)}]
    out = []
    now = utcnow()
    for rule in rules:
        item = {"code": rule["code"], "title": rule["title"], "authority": rule["authority"], "status": "ok", "detail": ""}
        if rule.get("automatic"):
            item["detail"] = "Handled automatically by this portal."
        elif rule["cadence"] == "per_meeting":
            soon = conn.execute(select(meetings).where(meetings.c.starts_at > now,
                                                       meetings.c.starts_at < now + dt.timedelta(days=14),
                                                       meetings.c.status.in_(["draft", "posted"]))).mappings().all()
            late = [m for m in soon if m["status"] == "draft" and m["starts_at"] - now < dt.timedelta(hours=72)]
            if late:
                item["status"] = "bad"
                item["detail"] = (f"{len(late)} meeting(s) within 72 hours are not posted: "
                                  + "; ".join(m["title"] for m in late))
            else:
                item["detail"] = f"{len([m for m in soon if m['status'] == 'posted'])} upcoming meeting(s) posted."
        else:
            latest = conn.execute(select(func.max(postings.c.posted_at)).where(
                postings.c.rule_code == rule["code"], postings.c.published.is_(True))).scalar()
            if latest is None:
                item["status"] = "warn" if rule["cadence"] in ("per_election",) else "bad"
                item["detail"] = "Nothing posted yet." if rule["cadence"] != "per_election" else \
                    "Nothing posted. Post this before each election."
            elif rule.get("max_age_days") and (now - latest).days > int(rule["max_age_days"]):
                item["status"] = "warn"
                item["detail"] = f"Last posted {(now - latest).days} days ago; it may be out of date."
            else:
                item["detail"] = f"Last posted {latest:%B %d, %Y}."
        out.append(item)
    return out


# ADA Title II web rule (28 CFR 35.200), compliance dates as amended by the
# April 2026 interim final rule, 91 Fed. Reg. 20902. Update here if DOJ changes them.
TITLE_II_LARGE = dt.date(2027, 4, 26)   # population 50,000 or more
TITLE_II_SMALL = dt.date(2028, 4, 26)   # population under 50,000, and all special districts


def title2_deadline(site: dict) -> tuple[dt.date | None, str]:
    """The WCAG 2.1 AA compliance date for this government, and why."""
    kind = site.get("jurisdiction_type")
    pop = site.get("population")
    if kind == "special_district":
        return TITLE_II_SMALL, "special district governments have the later date regardless of population"
    if not pop:
        return None, "enter your population in Settings > Site identity to see your date"
    if int(pop) >= 50_000:
        return TITLE_II_LARGE, f"population {int(pop):,} is 50,000 or more"
    return TITLE_II_SMALL, f"population {int(pop):,} is under 50,000"
