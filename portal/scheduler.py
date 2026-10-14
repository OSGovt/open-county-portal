"""Nightly maintenance inside the portal, for hosting platforms without a
scheduler (set PORTAL_NIGHTLY_IN_APP=true). On a normal server the systemd
timer runs 'countyctl nightly' instead, which also takes backups; here the
platform's managed database backups take that role.

Every worker process starts the thread, but a PostgreSQL advisory lock lets
only one of them do the work each night.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

from sqlalchemy import text

log = logging.getLogger("portal.nightly")
LOCK_ID = 7320147
RUN_AT_UTC = dt.time(8, 30)  # 2:30 or 3:30 a.m. Central


def _seconds_until_next_run(now: dt.datetime) -> float:
    target = dt.datetime.combine(now.date(), RUN_AT_UTC, dt.timezone.utc)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


def run_once() -> bool:
    """Run the nightly jobs if no other process is. Returns True if this process ran them."""
    from .db import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID}).scalar():
            return False
        try:
            from . import cli
            for args in (["export-bulk"], ["purge-uploads"]):
                try:
                    cli.main(args)
                except Exception:  # keep going; the next night tries again
                    log.exception("nightly job %s failed", args[0])
            return True
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})
            conn.commit()


def _loop() -> None:
    from .settings import get_settings
    if not (get_settings().bulk_dir / "latest" / "manifest.json").exists():
        time.sleep(30)  # let the site finish starting, then make the first bulk files
        run_once()
    while True:
        time.sleep(_seconds_until_next_run(dt.datetime.now(dt.timezone.utc)))
        run_once()
        time.sleep(120)


def start() -> None:
    threading.Thread(target=_loop, name="portal-nightly", daemon=True).start()
