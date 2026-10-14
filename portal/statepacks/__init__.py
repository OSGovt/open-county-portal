"""State packs: everything that differs from state to state, as data.

A pack is a YAML file at portal/statepacks/<code>/pack.yaml. Packs are read
at runtime (postings rules, forms, notices) and applied once at setup to seed
offices, services and fee templates into the database, where the county then
edits and confirms them.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.engine import Connection

from ..db import fees, offices, services

PACK_DIR = Path(__file__).parent
REQUIRED_TOP = ["pack", "name", "version", "status", "offices", "records", "public_information",
                "payments", "postings", "handoffs", "fees", "services", "forms"]
FIELD_TYPES = {"text", "email", "tel", "date", "textarea", "select", "radio", "checkbox", "file", "number"}


class PackError(ValueError):
    pass


def available() -> list[str]:
    return sorted(p.name for p in PACK_DIR.iterdir() if (p / "pack.yaml").exists() and not p.name.startswith("_"))


@lru_cache(maxsize=16)
def load(code: str) -> dict[str, Any]:
    path = PACK_DIR / code / "pack.yaml"
    if not path.exists():
        raise PackError(f"No state pack named '{code}'. Available: {', '.join(available()) or 'none'}.")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    problems = validate(data)
    if problems:
        raise PackError(f"State pack '{code}' has problems:\n- " + "\n- ".join(problems))
    return data


def validate(data: dict) -> list[str]:
    problems: list[str] = []
    for key in REQUIRED_TOP:
        if key not in data:
            problems.append(f"missing top-level section '{key}'")
    office_slugs = {o.get("slug") for o in data.get("offices") or []}
    office_slugs |= {o.get("slug") for o in ((data.get("district_profile") or {}).get("offices") or [])}
    fee_codes = set()
    for fee in (data.get("fees") or []):
        for k in ("code", "office", "label", "amount"):
            if k not in fee:
                problems.append(f"fee {fee.get('code', '?')} is missing '{k}'")
        if fee.get("office") not in office_slugs:
            problems.append(f"fee {fee.get('code')} names unknown office '{fee.get('office')}'")
        if not fee.get("statute"):
            problems.append(f"fee {fee.get('code')} has no statute or source")
        fee_codes.add(fee.get("code"))
    for svc in (data.get("services") or []) + ((data.get("district_profile") or {}).get("services") or []):
        for k in ("slug", "title", "office"):
            if k not in svc:
                problems.append(f"service {svc.get('slug', '?')} is missing '{k}'")
    for rule in data.get("postings") or []:
        for k in ("code", "title", "authority", "cadence"):
            if k not in rule:
                problems.append(f"posting rule {rule.get('code', '?')} is missing '{k}'")
    for slug, form in (data.get("forms") or {}).items():
        if not form.get("title"):
            problems.append(f"form {slug} has no title")
        if form.get("fee_code") and form["fee_code"] not in fee_codes:
            problems.append(f"form {slug} uses unknown fee '{form['fee_code']}'")
        names = set()
        for f in form.get("fields") or []:
            if f.get("type") not in FIELD_TYPES:
                problems.append(f"form {slug} field {f.get('name')} has unknown type '{f.get('type')}'")
            if f.get("name") in names:
                problems.append(f"form {slug} repeats field name '{f.get('name')}'")
            names.add(f.get("name"))
            if f.get("type") in ("select", "radio") and not f.get("options"):
                problems.append(f"form {slug} field {f.get('name')} needs options")
    return problems


def profile(pack: dict, jurisdiction_type: str) -> dict:
    """The offices/services/fees/forms/postings that apply to this kind of jurisdiction."""
    if jurisdiction_type == "county" or not pack.get("district_profile"):
        return {"offices": pack["offices"], "services": pack["services"], "fees": pack["fees"],
                "forms": pack["forms"], "postings": pack["postings"]}
    d = pack["district_profile"]
    allowed = set(d.get("postings") or [])
    forms = {k: v for k, v in (pack.get("forms") or {}).items() if k in set(d.get("forms") or [])}
    return {"offices": d.get("offices") or [], "services": d.get("services") or [],
            "fees": d.get("fees") or [], "forms": forms,
            "postings": [p for p in pack["postings"] if p["code"] in allowed]}


def apply(conn: Connection, code: str, jurisdiction_type: str, effective_from: dt.date | None = None) -> dict[str, int]:
    """Seed offices, services and fee templates. Existing rows are left alone,
    so re-running never overwrites what the county has edited."""
    pack = load(code)
    prof = profile(pack, jurisdiction_type)
    effective_from = effective_from or dt.date.today()
    counts = {"offices": 0, "services": 0, "fees": 0}
    for i, o in enumerate(prof["offices"]):
        if conn.execute(select(offices.c.id).where(offices.c.slug == o["slug"])).first() is None:
            conn.execute(offices.insert().values(slug=o["slug"], name=o["name"], description=o.get("description"),
                                                 sort=(i + 1) * 10))
            counts["offices"] += 1
    for i, s in enumerate(prof["services"]):
        if conn.execute(select(services.c.id).where(services.c.slug == s["slug"])).first() is None:
            conn.execute(services.insert().values(
                slug=s["slug"], office_slug=s.get("office"), title=s["title"], summary=s.get("summary"),
                who=s.get("who"), needs=s.get("needs"), cost=s.get("cost"), timing=s.get("timing"),
                online_label=s.get("online_label"), online_target=s.get("online_target"),
                handoff=bool(s.get("handoff")), in_person=s.get("in_person"), body=s.get("body"),
                featured=bool(s.get("featured")), category=s.get("category"), keywords=s.get("keywords"),
                sort=(i + 1) * 10))
            counts["services"] += 1
    for f in prof["fees"]:
        if conn.execute(select(fees.c.id).where(fees.c.code == f["code"])).first() is None:
            conn.execute(fees.insert().values(
                code=f["code"], office_slug=f["office"], label=f["label"],
                amount_cents=int(round(float(f["amount"]) * 100)), unit=f.get("unit", "each"),
                statute=f.get("statute"), fund=f.get("fund", "General Fund"), effective_from=effective_from,
                counter=f.get("counter", True), confirmed=False, adopted_by="State pack template (confirm locally)"))
            counts["fees"] += 1
    return counts


def forms_for(code: str, jurisdiction_type: str) -> dict[str, dict]:
    return profile(load(code), jurisdiction_type)["forms"]


def posting_rules(code: str, jurisdiction_type: str) -> list[dict]:
    return profile(load(code), jurisdiction_type)["postings"]
