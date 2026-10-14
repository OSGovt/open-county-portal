"""Application commands, run inside the app container.

On the server, run them through the host tool:  sudo countyctl app <command>
For example:  sudo countyctl app user add --email clerk@county.gov --name "Pat Lee" --role records
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

from . import __version__, auth, config_store, statepacks
from .db import (audit, create_schema, get_engine, images, import_batches, instruments, meetings, parties, postings,
                 receivables, schema_version, tx, users)
from .settings import get_settings


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ---- setup ------------------------------------------------------------------------

def cmd_setup(a) -> int:
    settings = get_settings()
    settings.ensure_dirs()
    create_schema()
    _extensions()
    with tx() as conn:
        site = config_store.get(conn, "site")
        if a.name:
            site["jurisdiction_name"] = a.name
        if a.type:
            site["jurisdiction_type"] = a.type
        if a.state:
            pack = statepacks.load(a.state)
            site["state"] = a.state
            site["state_name"] = pack["name"]
        if getattr(a, "state_name", None):
            site["state_name"] = a.state_name
        config_store.put(conn, "site", site, actor="setup", note="Initial setup")
        counts = statepacks.apply(conn, site["state"], site["jurisdiction_type"])
        say(f"State pack '{site['state']}' applied: {counts['offices']} offices, {counts['services']} services, "
            f"{counts['fees']} fee templates added.")
        if a.admin_email:
            exists = conn.execute(select(users.c.id).where(users.c.email == a.admin_email.lower())).first()
            if exists:
                say(f"Administrator {a.admin_email} already exists; not changed.")
            else:
                temp = auth.create_user(conn, a.admin_email, a.admin_name or "Administrator", ["admin"], actor="setup")
                _write_secret_note(a.admin_email, temp)
                say("")
                say("Administrator account created.")
                say(f"  Email:              {a.admin_email}")
                say(f"  Temporary password: {temp}")
                say("You'll choose your own password and set up a phone code the first time you sign in.")
    say("Setup complete.")
    return 0


def _write_secret_note(email: str, temp: str) -> None:
    path = get_settings().data_dir / "status" / "first-admin.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"First administrator: {email}\nTemporary password: {temp}\n"
                    "Delete this file after you sign in for the first time.\n", encoding="utf-8")
    path.chmod(0o600)


def _extensions() -> None:
    """Fast name search on large record sets (Postgres trigram index)."""
    from sqlalchemy import text
    try:
        with tx() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_parties_name_trgm ON parties USING gin (name_norm gin_trgm_ops)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_instruments_legal_trgm ON instruments USING gin (legal_description gin_trgm_ops)"))
    except Exception as exc:  # works without it, just slower on millions of rows
        say(f"Note: fast-search index not created ({exc.__class__.__name__}). Search still works.")


# ---- users ------------------------------------------------------------------------

def cmd_user(a) -> int:
    with tx() as conn:
        if a.action == "add":
            temp = auth.create_user(conn, a.email, a.name or a.email, a.role or [], a.office or [], actor="cli")
            say(f"Account created for {a.email}. Temporary password: {temp}")
            say("They will choose their own password and set up a phone code at first sign-in.")
        elif a.action == "reset":
            row = conn.execute(select(users).where(users.c.email == a.email.lower())).mappings().first()
            if row is None:
                say(f"No account for {a.email}.")
                return 1
            temp = auth.temporary_password()
            conn.execute(users.update().where(users.c.id == row["id"]).values(
                password_hash=auth.hash_password(temp), must_change_password=True, totp_secret=auth.new_totp_secret(),
                mfa_enrolled=False, failed_logins=0, locked_until=None, active=True))
            audit(conn, "cli", "user.reset", "user", a.email)
            say(f"Reset {a.email}. Temporary password: {temp}. They will set up their phone code again at sign-in.")
        elif a.action == "disable":
            n = conn.execute(users.update().where(users.c.email == a.email.lower()).values(active=False)).rowcount
            audit(conn, "cli", "user.disable", "user", a.email)
            say("Account disabled." if n else f"No account for {a.email}.")
        elif a.action == "list":
            for r in conn.execute(select(users).order_by(users.c.email)).mappings():
                state = "active" if r["active"] else "disabled"
                say(f"{r['email']:40} {r['name']:28} {','.join(r['roles']):30} {state}")
    return 0


# ---- demo data ------------------------------------------------------------------

DEMO_BATCH_SOURCE = "demo-sample-data"


def _demo_page(title: str, lines: list[str]) -> bytes:
    from PIL import Image, ImageDraw
    from .images import _font
    page = Image.new("L", (1275, 1650), 255)
    d = ImageDraw.Draw(page)
    d.text((100, 80), "SAMPLE DOCUMENT - NOT A REAL RECORD", fill=90, font=_font(30))
    d.text((100, 170), title, fill=0, font=_font(52))
    y = 280
    for line in lines:
        d.text((100, y), line, fill=0, font=_font(30))
        y += 52
    buf = io.BytesIO()
    page.save(buf, format="PNG")
    return buf.getvalue()


def cmd_demo(a) -> int:
    settings = get_settings()
    with tx() as conn:
        if a.remove:
            batch = conn.execute(select(import_batches.c.id).where(import_batches.c.source == DEMO_BATCH_SOURCE)).scalar()
            if batch:
                conn.execute(delete(instruments).where(instruments.c.import_batch == batch))
                conn.execute(delete(receivables).where(receivables.c.import_batch == batch))
                conn.execute(import_batches.update().where(import_batches.c.id == batch).values(status="undone"))
            conn.execute(delete(meetings).where(meetings.c.title.like("SAMPLE:%")))
            conn.execute(delete(postings).where(postings.c.title.like("SAMPLE:%")))
            audit(conn, "cli", "demo.remove")
            say("Sample data removed.")
            return 0
        if conn.execute(select(import_batches.c.id).where(import_batches.c.source == DEMO_BATCH_SOURCE,
                                                          import_batches.c.status != "undone")).first():
            say("Sample data is already loaded. Remove it with: countyctl app demo --remove")
            return 0
        batch = conn.execute(import_batches.insert().values(kind="demo", source=DEMO_BATCH_SOURCE, status="loaded",
                                                            finished_at=dt.datetime.now(dt.timezone.utc))
                             .returning(import_batches.c.id)).scalar_one()
        samples = [
            ("2026-004812", "Warranty Deed", dt.date(2026, 9, 28), ["SAMPLE RANCH HOLDINGS LLC"], ["J Q RESIDENT"],
             "SAMPLE SURVEY, ABSTRACT 0, 12.5 ACRES", 3),
            ("2026-004790", "Deed of Trust", dt.date(2026, 9, 28), ["J Q RESIDENT"], ["SAMPLE COMMUNITY BANK"],
             "SAMPLE SURVEY, ABSTRACT 0, 12.5 ACRES", 4),
            ("2026-004355", "Release of Lien", dt.date(2026, 9, 10), ["SAMPLE COMMUNITY BANK"], ["A B HOMEOWNER"],
             "SAMPLE CREEK ESTATES, LOT 7, BLOCK 2", 1),
            ("2025-011902", "Plat", dt.date(2025, 12, 2), ["SAMPLE CREEK ESTATES LTD"], ["THE PUBLIC"],
             "SAMPLE CREEK ESTATES, LOTS 1-24", 2),
            ("2024-002217", "Warranty Deed", dt.date(2024, 3, 14), ["A B HOMEOWNER", "C D HOMEOWNER"], ["E F BUYER"],
             "SAMPLE CREEK ESTATES, LOT 7, BLOCK 2", 2),
        ]
        from .images import sha256_file
        for number, dtype, rdate, grantors, grantees, legal, pages in samples:
            iid = conn.execute(instruments.insert().values(
                instrument_number=number, doc_type=dtype, recorded_date=rdate, legal_description=legal,
                property_id="SAMPLE-" + number[-4:], page_count=pages, import_batch=batch, status="public")
                .returning(instruments.c.id)).scalar_one()
            from .records import normalize_name
            for g in grantors:
                conn.execute(parties.insert().values(instrument_id=iid, role="grantor", name=g, name_norm=normalize_name(g)))
            for g in grantees:
                conn.execute(parties.insert().values(instrument_id=iid, role="grantee", name=g, name_norm=normalize_name(g)))
            for seq in range(1, pages + 1):
                rel = Path("demo") / f"{number}-{seq}.png"
                path = settings.images_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(_demo_page(dtype.upper(), [f"Instrument {number}, page {seq} of {pages}",
                                                            f"Recorded {rdate:%B %d, %Y}",
                                                            f"Grantor: {'; '.join(grantors)}",
                                                            f"Grantee: {'; '.join(grantees)}",
                                                            f"Legal description: {legal}",
                                                            "This page exists to train staff and test the portal."]))
                conn.execute(images.insert().values(instrument_id=iid, seq=seq, path=str(rel), frame=0, mime="image/png",
                                                    sha256=sha256_file(path), bytes=path.stat().st_size,
                                                    ocr_text=f"SAMPLE DOCUMENT {dtype.upper()} Instrument {number} page {seq}"))
        for acct, name, addr, cents, kind, office, desc in [
            ("R000123", "J Q RESIDENT", "100 SAMPLE RD", 218437, "property_tax", "tax-office", "2026 property tax"),
            ("R000456", "A B HOMEOWNER", "7 SAMPLE CREEK DR", 96512, "property_tax", "tax-office", "2026 property tax"),
            ("CR-26-0042", "J Q RESIDENT", "", 25600, "court", "district-clerk", "Court costs, case CR-26-0042"),
        ]:
            if conn.execute(select(receivables.c.id).where(receivables.c.kind == kind, receivables.c.account == acct)).first():
                continue
            conn.execute(receivables.insert().values(kind=kind, office_slug=office, account=acct, name=name, address=addr,
                                                     amount_due_cents=cents, description=desc, import_batch=batch,
                                                     due_date=dt.date(dt.date.today().year + 1, 1, 31)))
        starts = dt.datetime.now(dt.timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0) + dt.timedelta(days=10)
        conn.execute(meetings.insert().values(
            body="Commissioners Court", title="SAMPLE: Regular meeting", starts_at=starts, location="Courthouse",
            status="posted", posted_at=dt.datetime.now(dt.timezone.utc),
            agenda="1. Call to order\n2. Public comment\n3. Consider approval of bills and payroll\n4. Adjourn"))
        conn.execute(postings.insert().values(rule_code="tax-rate-budget", title="SAMPLE: Tax rate and budget information",
                                              body="Sample posting used for training.", published=True))
        audit(conn, "cli", "demo.load")
    say("Sample data loaded: 5 records with page images, 3 bills, 1 meeting, 1 notice.")
    say("Everything sample is labeled SAMPLE. Remove it before going live: countyctl app demo --remove")
    return 0


# ---- maintenance -----------------------------------------------------------------

def cmd_export_bulk(a) -> int:
    from .bulk import export
    with get_engine().connect() as conn:
        path = export(conn)
    say(f"Bulk files written to {path}")
    return 0


def cmd_postings_check(a) -> int:
    from .compliance import check_postings
    with get_engine().connect() as conn:
        rows = check_postings(conn)
    bad = 0
    for r in rows:
        mark = {"ok": "OK   ", "warn": "CHECK", "bad": "MISSING"}[r["status"]]
        bad += r["status"] == "bad"
        say(f"{mark}  {r['title']} ({r['authority']}): {r['detail']}")
    return 1 if bad else 0


def cmd_ocr(a) -> int:
    from .images import ocr, ocr_available
    if not ocr_available():
        say("Tesseract is not installed in this container; OCR is skipped.")
        return 1
    settings = get_settings()
    done = 0
    with get_engine().connect() as conn:
        todo = conn.execute(select(images.c.id, images.c.path, images.c.frame)
                            .where(images.c.ocr_text.is_(None)).limit(a.limit)).all()
    for row in todo:
        text = ocr(settings.images_dir / row.path, row.frame)
        with tx() as conn:
            conn.execute(images.update().where(images.c.id == row.id).values(ocr_text=text))
        done += 1
        if done % 50 == 0:
            say(f"  {done} pages read...")
    say(f"OCR finished for {done} page(s).")
    return 0


def cmd_purge_uploads(a) -> int:
    """Delete sensitive uploads (such as ID photos) older than the retention period."""
    from .db import applications
    settings = get_settings()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=settings.id_upload_retention_days)
    removed = 0
    with tx() as conn:
        rows = conn.execute(select(applications).where(applications.c.created_at < cutoff)).mappings().all()
        for r in rows:
            kept = []
            for u in r["uploads"] or []:
                if u.get("sensitive"):
                    p = settings.uploads_dir / u["path"]
                    if p.exists():
                        p.unlink()
                        removed += 1
                    kept.append({**u, "path": None, "deleted": True})
                else:
                    kept.append(u)
            if kept != (r["uploads"] or []):
                conn.execute(applications.update().where(applications.c.id == r["id"]).values(uploads=kept))
        audit(conn, "cli", "uploads.purge", detail={"removed": removed})
    say(f"Deleted {removed} sensitive upload(s) older than {settings.id_upload_retention_days} days.")
    return 0


def cmd_check(a) -> int:
    """Quick self-test used by the installer and 'countyctl doctor'."""
    ok = True
    try:
        with get_engine().connect() as conn:
            v = schema_version(conn)
            n = conn.execute(select(func.count()).select_from(users)).scalar_one()
        say(f"Database: OK (schema version {v}, {n} staff account(s))")
    except Exception as exc:
        say(f"Database: FAILED ({exc})")
        ok = False
    s = get_settings()
    for d in (s.images_dir, s.uploads_dir, s.bulk_dir):
        if not d.exists():
            say(f"Folder missing: {d}")
            ok = False
    say(f"Version: {__version__}")
    return 0 if ok else 1


def cmd_upgrade_db(a) -> int:
    """Bring the database up to this version's schema. Runs at every start; safe to repeat."""
    import time
    for attempt in range(30):
        try:
            create_schema()
            break
        except Exception as exc:
            if attempt == 29:
                say(f"The database isn't reachable: {exc}")
                return 1
            time.sleep(2)
    _extensions()
    get_settings().ensure_dirs()
    say("Database is up to date.")
    return 0


def cmd_backup(a) -> int:
    from . import ops
    ops.backup(label=a.label or "", log=say)
    return 0


def cmd_list_backups(a) -> int:
    from . import ops
    rows = ops.list_backups()
    if not rows:
        say("No backups yet.")
    for b in rows:
        m = json.loads((b / "manifest.json").read_text())
        say(f"{b.name:40} version {m.get('version', '?'):8} database {m.get('db_dump_bytes', 0) / 1e6:8.1f} MB  "
            f"{m.get('files_copied', 0):,} new files")
    return 0


def cmd_verify_backup(a) -> int:
    from . import ops
    path = get_settings().backups_dir / a.name
    problems = ops.verify(path)
    if problems:
        for p in problems:
            say(f"PROBLEM: {p}")
        return 1
    say(f"Backup {a.name} is complete and readable.")
    return 0


def cmd_restore(a) -> int:
    from . import ops
    path = get_settings().backups_dir / a.name
    if not path.exists():
        say(f"No backup named {a.name}. List them with: countyctl backups")
        return 1
    if not a.yes:
        say("Restoring replaces the database and files. Use the host command 'countyctl restore', which stops the "
            "site and takes a safety backup first.")
        return 1
    ops.restore(path, log=say)
    return 0


def cmd_pack(a) -> int:
    if a.action == "list":
        for code in statepacks.available():
            p = statepacks.load(code)
            say(f"{code}  {p['name']}  version {p['version']}  status {p['status']}")
        return 0
    if a.action == "validate":
        import yaml
        data = yaml.safe_load(Path(a.path).read_text(encoding="utf-8"))
        problems = statepacks.validate(data)
        for p in problems:
            say(f"PROBLEM: {p}")
        say("Pack is valid." if not problems else f"{len(problems)} problem(s).")
        return 1 if problems else 0
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="countyctl app", description="Open County Portal application commands.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="Create the database and apply the state pack (safe to re-run).")
    s.add_argument("--name", help="Jurisdiction name, e.g. 'Example County'")
    s.add_argument("--type", choices=["county", "special_district", "school_district", "municipality"])
    s.add_argument("--state", help="Two-letter state pack code, e.g. tx (use _template if your state has no pack yet)")
    s.add_argument("--state-name", help="State name to show on the site when using _template, e.g. Ohio")
    s.add_argument("--admin-email")
    s.add_argument("--admin-name")
    s.set_defaults(fn=cmd_setup)

    u = sub.add_parser("user", help="Manage staff accounts.")
    u.add_argument("action", choices=["add", "reset", "disable", "list"])
    u.add_argument("--email")
    u.add_argument("--name")
    u.add_argument("--role", action="append", help=f"Repeat for several. Roles: {', '.join(auth.ROLES)}")
    u.add_argument("--office", action="append", help="Office slug for cashiers, e.g. county-clerk. Repeatable.")
    u.set_defaults(fn=cmd_user)

    d = sub.add_parser("demo", help="Load (or --remove) clearly labeled sample data for training.")
    d.add_argument("--remove", action="store_true")
    d.set_defaults(fn=cmd_demo)

    sub.add_parser("export-bulk", help="Write the daily bulk data files now.").set_defaults(fn=cmd_export_bulk)
    sub.add_parser("postings-check", help="Report required postings that are missing or late.").set_defaults(fn=cmd_postings_check)
    o = sub.add_parser("ocr", help="Read text from page images that don't have it yet.")
    o.add_argument("--limit", type=int, default=5000)
    o.set_defaults(fn=cmd_ocr)
    sub.add_parser("purge-uploads", help="Delete sensitive uploads past the retention period.").set_defaults(fn=cmd_purge_uploads)
    sub.add_parser("check", help="Self-test.").set_defaults(fn=cmd_check)
    sub.add_parser("upgrade-db", help="Bring the database schema up to date (runs at every start).").set_defaults(fn=cmd_upgrade_db)
    bk = sub.add_parser("backup", help="Back up the database and files now.")
    bk.add_argument("--label", default="")
    bk.set_defaults(fn=cmd_backup)
    sub.add_parser("list-backups", help="List backups.").set_defaults(fn=cmd_list_backups)
    vb = sub.add_parser("verify-backup", help="Check that a backup is complete and readable.")
    vb.add_argument("name")
    vb.set_defaults(fn=cmd_verify_backup)
    rs = sub.add_parser("restore", help="Restore a backup (use the host command 'countyctl restore').")
    rs.add_argument("name")
    rs.add_argument("--yes", action="store_true")
    rs.set_defaults(fn=cmd_restore)

    pk = sub.add_parser("pack", help="List or validate state packs.")
    pk.add_argument("action", choices=["list", "validate"])
    pk.add_argument("path", nargs="?")
    pk.set_defaults(fn=cmd_pack)

    from .migrate import cli as migrate_cli
    migrate_cli.register(sub)

    a = p.parse_args(argv)
    if a.cmd == "user" and a.action != "list" and not a.email:
        p.error("--email is required")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
