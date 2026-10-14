"""Operational status for the dashboard: backups, bulk files, disk, email.

The host-side tools (countyctl) write small status files into the data
directory; the console only reads them, so the web application never needs
permission to control the server.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil

from . import notify
from .settings import get_settings


def _read(name: str) -> dict | None:
    path = get_settings().data_dir / "status" / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary() -> dict:
    s = get_settings()
    usage = shutil.disk_usage(s.data_dir)
    backup = _read("last_backup.json")
    bulk_manifest = s.bulk_dir / "latest" / "manifest.json"
    bulk = None
    if bulk_manifest.exists():
        try:
            bulk = json.loads(bulk_manifest.read_text())["generated_at"]
        except (OSError, ValueError, KeyError):
            bulk = None
    backup_age = None
    if backup and backup.get("finished_at"):
        try:
            backup_age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(backup["finished_at"])).days
        except ValueError:
            backup_age = None
    return {
        "disk_free_gb": round(usage.free / 1e9, 1),
        "disk_used_pct": round(100 * usage.used / usage.total),
        "backup": backup,
        "backup_age_days": backup_age,
        "bulk_generated_at": bulk,
        "email_configured": notify.configured(),
        "last_update": _read("last_update.json"),
    }
