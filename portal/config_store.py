"""Settings edited in the staff console, with full history.

Each key holds one JSON value. Saving a value copies it into
``setting_history`` first, so the console can show every earlier version
and restore any of them.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from .db import setting_history, settings_table, utcnow

DEFAULTS: dict[str, Any] = {
    "site": {
        "jurisdiction_name": "Example County",
        "jurisdiction_type": "county",  # county | special_district | school_district | municipality
        "state": "tx",
        "state_name": "Texas",
        "tagline": "",
        "address": "",
        "phone": "",
        "email": "",
        "population": None,
        "census_government_id": "",
        "fips": "",
        "appraisal_district_url": "",
        "accessibility_contact": "",
        "language": "en",
        "timezone": "America/Chicago",
    },
    "alert": {"enabled": False, "level": "warning", "title": "", "body": "", "link_text": "", "link_url": ""},
    "payments": {
        "processor": "test",
        "card_fee_percent": 0.0,
        "card_fee_flat_cents": 0,
        "card_fee_min_cents": 0,
        "ach_fee_flat_cents": 0,
        "fee_authority": "",
        "methods": ["card", "ach"],
        "processor_settings": {},
    },
    "records": {
        "enabled": True,
        "free_downloads": True,
        "certified_fee_code": "cert",
        "certified_page_fee_code": "copy_page",
        "show_property_id": True,
    },
    "open_data": {
        "data_terms": "Public records published by this jurisdiction. No restrictions are applied by this software; see the jurisdiction's terms.",
        "license_url": "",
        "contact_name": "Open data contact",
        "contact_email": "",
        "publish_receivables": False,
    },
    "golive": {"checked": []},
}


def get(conn: Connection, key: str) -> Any:
    row = conn.execute(select(settings_table.c.value).where(settings_table.c.key == key)).first()
    base = copy.deepcopy(DEFAULTS.get(key))
    if row is None:
        return base
    value = row[0]
    if isinstance(base, dict) and isinstance(value, dict):
        base.update(value)
        return base
    return value


def put(conn: Connection, key: str, value: Any, actor: str | None = None, note: str | None = None) -> None:
    existing = conn.execute(select(settings_table.c.value).where(settings_table.c.key == key)).first()
    if existing is None:
        conn.execute(settings_table.insert().values(key=key, value=value, updated_by=actor, updated_at=utcnow()))
    else:
        conn.execute(settings_table.update().where(settings_table.c.key == key)
                     .values(value=value, updated_by=actor, updated_at=utcnow()))
    conn.execute(setting_history.insert().values(key=key, value=value, changed_by=actor, note=note))


def history(conn: Connection, key: str, limit: int = 50) -> list[dict]:
    rows = conn.execute(select(setting_history).where(setting_history.c.key == key)
                        .order_by(setting_history.c.id.desc()).limit(limit)).mappings().all()
    return [dict(r) for r in rows]


def restore(conn: Connection, key: str, history_id: int, actor: str | None) -> Any:
    row = conn.execute(select(setting_history).where(setting_history.c.id == history_id,
                                                     setting_history.c.key == key)).mappings().first()
    if row is None:
        raise KeyError("That version no longer exists.")
    put(conn, key, row["value"], actor=actor, note=f"Restored version from {row['changed_at']:%Y-%m-%d %H:%M}")
    return row["value"]
