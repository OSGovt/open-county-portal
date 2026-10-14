"""Backups and restores.

A backup is a folder <data>/backups/<YYYYmmdd-HHMMSS>/ containing:
  db.dump         PostgreSQL custom-format dump (pg_dump -Fc)
  files/          a snapshot of images/, files/ and uploads/. Unchanged files
                  are hard links to the previous snapshot, so nightly backups
                  of large image collections take seconds and little space.
  manifest.json   size and SHA-256 of db.dump, file count, versions

Backups on the same disk protect against mistakes, not disk failure. Copy
them off the server: set PORTAL_BACKUP_COPY_CMD (see docs/admin/backups.md)
and every backup is copied automatically after it finishes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse, unquote

from . import __version__
from .settings import get_settings

SNAPSHOT_DIRS = ("images", "files", "uploads")


def _pg_env() -> tuple[list[str], dict]:
    url = urlparse(get_settings().database_url.replace("+psycopg", ""))
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = unquote(url.password)
    args = ["-d", url.path.lstrip("/") or "portal"]
    if url.hostname:
        args += ["-h", url.hostname]
    if url.port:
        args += ["-p", str(url.port)]
    if url.username:
        args += ["-U", unquote(url.username)]
    q = dict(p.split("=", 1) for p in url.query.split("&") if "=" in p)
    if "host" in q:
        args += ["-h", q["host"]]
    return args, env


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _status(name: str, payload: dict) -> None:
    d = get_settings().data_dir / "status"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{name}.tmp"
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(d / name)


def list_backups() -> list[Path]:
    root = get_settings().backups_dir
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()], reverse=True)


def backup(label: str = "", keep: int | None = None, log=print) -> Path:
    s = get_settings()
    keep = keep or int(os.environ.get("PORTAL_BACKUP_KEEP", "14"))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = s.backups_dir / (stamp + (f"-{label}" if label else ""))
    work = dest.with_name(dest.name + ".partial")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    started = dt.datetime.now(dt.timezone.utc)
    log("Backing up the database...")
    args, env = _pg_env()
    subprocess.run(["pg_dump", "-Fc", "--no-owner", "-f", str(work / "db.dump"), *args], check=True, env=env, timeout=6 * 3600)
    previous = next(iter(list_backups()), None)
    log("Snapshotting images, files and uploads...")
    copied = linked = 0
    for sub in SNAPSHOT_DIRS:
        src_root = s.data_dir / sub
        if not src_root.exists():
            continue
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(s.data_dir)
            target = work / "files" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            prev = previous / "files" / rel if previous else None
            st = src.stat()
            if prev is not None and prev.exists():
                pst = prev.stat()
                if pst.st_size == st.st_size and int(pst.st_mtime) == int(st.st_mtime):
                    try:
                        os.link(prev, target)
                        linked += 1
                        continue
                    except OSError:
                        pass
            shutil.copy2(src, target)
            copied += 1
    manifest = {"version": __version__, "started_at": started.isoformat(),
                "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "label": label,
                "db_dump_bytes": (work / "db.dump").stat().st_size, "db_dump_sha256": _sha(work / "db.dump"),
                "files_copied": copied, "files_linked": linked}
    (work / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    work.rename(dest)
    _status("last_backup.json", {**manifest, "path": str(dest)})
    log(f"Backup complete: {dest.name} ({copied} new or changed files, {linked} unchanged)")
    # Retention: keep the newest N automatic backups; labeled ones (pre-update, manual) are kept 60 days.
    def labeled(b: Path) -> bool:  # "20261013-123456" is automatic; "20261013-123456-pre-update" is labeled
        return len(b.name) > 15

    auto = [b for b in list_backups() if not labeled(b)]
    for old in auto[keep:]:
        shutil.rmtree(old, ignore_errors=True)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)
    for b in list_backups():
        if labeled(b):
            try:
                when = dt.datetime.strptime(b.name[:15], "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc)
                if when < cutoff:
                    shutil.rmtree(b, ignore_errors=True)
            except ValueError:
                continue
    copy_cmd = os.environ.get("PORTAL_BACKUP_COPY_CMD")
    if copy_cmd:
        log("Copying the backup off the server...")
        r = subprocess.run(copy_cmd.replace("{path}", str(dest)), shell=True, timeout=12 * 3600)
        _status("last_offsite.json", {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "ok": r.returncode == 0,
                                      "path": str(dest)})
        log("Off-site copy " + ("finished." if r.returncode == 0 else f"FAILED (exit {r.returncode})."))
    return dest


def verify(path: Path) -> list[str]:
    """Check a backup is complete and its database dump is intact."""
    problems = []
    mf = path / "manifest.json"
    if not mf.exists():
        return ["manifest.json is missing; this backup did not finish."]
    m = json.loads(mf.read_text())
    dump = path / "db.dump"
    if not dump.exists():
        problems.append("db.dump is missing.")
    elif _sha(dump) != m.get("db_dump_sha256"):
        problems.append("db.dump does not match its checksum; it is damaged.")
    else:
        r = subprocess.run(["pg_restore", "--list", str(dump)], capture_output=True)
        if r.returncode != 0:
            problems.append("pg_restore cannot read db.dump.")
    return problems


def restore(path: Path, log=print) -> None:
    """Replace the database and files with a backup. The caller must stop the
    web service first and should take a fresh backup before calling this."""
    s = get_settings()
    problems = verify(path)
    if problems:
        raise RuntimeError("This backup can't be restored: " + " ".join(problems))
    log("Restoring the database...")
    args, env = _pg_env()
    subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "-1", *args, str(path / "db.dump")],
                   check=True, env=env, timeout=6 * 3600)
    log("Restoring images, files and uploads...")
    for sub in SNAPSHOT_DIRS:
        live = s.data_dir / sub
        snap = path / "files" / sub
        aside = s.data_dir / f".{sub}.before-restore"
        if aside.exists():
            shutil.rmtree(aside)
        if live.exists():
            live.rename(aside)
        if snap.exists():
            shutil.copytree(snap, live, copy_function=shutil.copy2)
        else:
            live.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(aside, ignore_errors=True)
    shutil.rmtree(s.cache_dir, ignore_errors=True)
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    _status("last_restore.json", {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "from": path.name})
    log(f"Restore from {path.name} complete.")
