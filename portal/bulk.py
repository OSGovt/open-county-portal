"""Daily bulk files for the open data API.

Writes CSV and JSON Lines files plus a manifest with row counts and SHA-256
checksums to <data>/bulk/<date>/, then points <data>/bulk/latest at it.
Keeps the last 7 days. Run nightly by the installer's scheduled job, or by
hand with: countyctl app export-bulk
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Connection

from . import fees as fee_mod
from .db import images, instruments, meetings, offices, parties, pia_requests, postings, services, utcnow
from .settings import get_settings

KEEP_DAYS = 7


def _iso(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(conn: Connection) -> Path:
    settings = get_settings()
    base = settings.site_url
    stamp = dt.date.today().isoformat()
    out = settings.bulk_dir / f"{stamp}.tmp"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    counts: dict[str, int] = {}

    # Instruments: one CSV row and one JSON line per public instrument.
    party_map: dict[int, dict[str, list[str]]] = {}
    for p in conn.execution_options(stream_results=True).execute(
            select(parties.c.instrument_id, parties.c.role, parties.c.name).order_by(parties.c.id)):
        party_map.setdefault(p.instrument_id, {"grantor": [], "grantee": []}).setdefault(p.role, []).append(p.name)
    img_map: dict[int, list[dict]] = {}
    for i in conn.execution_options(stream_results=True).execute(
            select(images.c.instrument_id, images.c.seq, images.c.sha256).order_by(images.c.instrument_id, images.c.seq)):
        img_map.setdefault(i.instrument_id, []).append({"seq": i.seq, "sha256": i.sha256})
    cols = ["instrument_number", "doc_type", "recorded_date", "book", "page", "grantors", "grantees",
            "legal_description", "property_id", "page_count", "remarks", "updated_at", "url"]
    n = 0
    with (out / "instruments.csv").open("w", newline="", encoding="utf-8") as fc, \
            (out / "instruments.jsonl").open("w", encoding="utf-8") as fj:
        w = csv.writer(fc)
        w.writerow(cols)
        for r in conn.execution_options(stream_results=True).execute(
                select(instruments).where(instruments.c.status == "public").order_by(instruments.c.id)).mappings():
            ps = party_map.get(r["id"], {})
            url = f"{base}/records/{r['instrument_number']}"
            w.writerow([r["instrument_number"], r["doc_type"], _iso(r["recorded_date"]), r["book"], r["page"],
                        "; ".join(ps.get("grantor", [])), "; ".join(ps.get("grantee", [])), r["legal_description"],
                        r["property_id"], r["page_count"], r["remarks"], _iso(r["updated_at"]), url])
            doc = {"instrument_number": r["instrument_number"], "doc_type": r["doc_type"],
                   "recorded_date": _iso(r["recorded_date"]), "book": r["book"], "page": r["page"],
                   "grantors": ps.get("grantor", []), "grantees": ps.get("grantee", []),
                   "legal_description": r["legal_description"], "property_id": r["property_id"],
                   "page_count": r["page_count"], "remarks": r["remarks"], "updated_at": _iso(r["updated_at"]),
                   "url": url,
                   "images": [{"seq": i["seq"], "sha256": i["sha256"],
                               "url": f"{base}/records/{r['instrument_number']}/pages/{i['seq']}.png"}
                              for i in img_map.get(r["id"], [])]}
            fj.write(json.dumps(doc, ensure_ascii=False) + "\n")
            n += 1
    counts["instruments"] = n

    def dump_json(name: str, rows: list[dict]) -> None:
        (out / f"{name}.json").write_text(json.dumps([{k: _iso(v) for k, v in r.items()} for r in rows],
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
        counts[name] = len(rows)

    dump_json("meetings", [dict(r) for r in conn.execute(select(meetings).where(meetings.c.status.in_(["posted", "held", "cancelled"]))).mappings()])
    dump_json("postings", [dict(r) for r in conn.execute(select(postings).where(postings.c.published.is_(True))).mappings()])
    dump_json("services", [dict(r) for r in conn.execute(select(services).where(services.c.published.is_(True))).mappings()])
    dump_json("offices", [{k: v for k, v in dict(r).items() if k != "merchant_account"}
                          for r in conn.execute(select(offices).where(offices.c.active.is_(True))).mappings()])
    dump_json("fees", fee_mod.all_current(conn) + fee_mod.scheduled(conn))
    dump_json("public_information", [{k: r[k] for k in ("number", "description", "response", "received_at", "status")}
                                     for r in conn.execute(select(pia_requests).where(pia_requests.c.publish_response.is_(True))).mappings()])

    manifest = {"generated_at": utcnow().isoformat(), "site": base, "files": []}
    for f in sorted(out.iterdir()):
        manifest["files"].append({"name": f.name, "bytes": f.stat().st_size, "sha256": _sha(f),
                                  "rows": counts.get(f.stem), "url": f"{base}/api/v1/bulk/{f.name}"})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    final = settings.bulk_dir / stamp
    if final.exists():
        shutil.rmtree(final)
    out.rename(final)
    latest = settings.bulk_dir / "latest"
    tmp_link = settings.bulk_dir / "latest.tmp"
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()
    tmp_link.symlink_to(final.name)
    tmp_link.replace(latest)
    cutoff = dt.date.today() - dt.timedelta(days=KEEP_DAYS)
    for d in settings.bulk_dir.iterdir():
        try:
            if d.is_dir() and not d.is_symlink() and dt.date.fromisoformat(d.name) < cutoff:
                shutil.rmtree(d)
        except ValueError:
            continue
    return final
