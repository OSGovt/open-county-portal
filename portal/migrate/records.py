"""Records migration: from an old system's export into the portal.

The steps, each safe to repeat:
  1. inventory  look at the export folder and describe what's in it
  2. map        write mapping.yaml with best guesses for a person to confirm
  3. check      dry run: read everything, report problems, change nothing
  4. load       import as a numbered batch, copying images with checksums
  5. verify     compare a random sample against the source; HTML report
  6. undo       remove a whole batch (a backup is taken first)

Nothing in the export folder is ever modified.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from .. import images as img_mod
from ..db import audit, get_engine, images, import_batches, instruments, parties, tx, utcnow
from ..records import normalize_name
from ..settings import get_settings
from .tabular import TABLE_EXTS, guess_date_format, norm, parse_date, profile, read_rows

IMAGE_EXTS = {".tif", ".tiff", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}

# Column-name hints for the automatic mapping draft. Normalized: lowercase, no punctuation.
HINTS = {
    "instrument_number": ["instrumentnumber", "instrumentno", "instnum", "instno", "instrument", "docnumber", "docno",
                          "documentnumber", "filenumber", "clerkfilenumber", "recordingnumber"],
    "doc_type": ["doctype", "documenttype", "instrumenttype", "insttype", "type", "doctypedesc", "kind"],
    "recorded_date": ["recordeddate", "recdate", "recordingdate", "daterecorded", "filedate", "datefiled", "recorded"],
    "book": ["book", "volume", "vol", "bk"],
    "page": ["page", "pg", "startpage"],
    "grantors": ["grantor", "grantors", "grantorname", "from", "party1", "seller"],
    "grantees": ["grantee", "grantees", "granteename", "to", "party2", "buyer"],
    "party_name": ["name", "partyname", "fullname"],
    "party_role": ["role", "partytype", "partyrole", "direction", "grantorgrantee"],
    "legal_description": ["legal", "legaldescription", "legaldesc", "description", "subdivision"],
    "property_id": ["propertyid", "propid", "parcel", "parcelid", "cadid", "accountnumber", "geoid", "pid"],
    "page_count": ["pages", "pagecount", "numpages", "nopages"],
    "remarks": ["remarks", "notes", "comments", "memo"],
    "restricted": ["restricted", "confidential", "sealed", "private"],
}


def inventory(source: Path) -> dict:
    source = source.resolve()
    if not source.is_dir():
        raise SystemExit(f"{source} is not a folder. Point to the folder holding the export.")
    tables, image_counts, other = [], {}, 0
    total_bytes = 0
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        total_bytes += p.stat().st_size
        ext = p.suffix.lower()
        if ext in TABLE_EXTS and p.stat().st_size > 0:
            try:
                tables.append({"path": str(p.relative_to(source)), **profile(p)})
            except Exception as exc:
                tables.append({"path": str(p.relative_to(source)), "error": str(exc)})
        elif ext in IMAGE_EXTS:
            image_counts[ext] = image_counts.get(ext, 0) + 1
        else:
            other += 1
    image_dirs = sorted({str(p.parent.relative_to(source)) for p in source.rglob("*")
                         if p.is_file() and p.suffix.lower() in IMAGE_EXTS})[:20]
    return {"source": str(source), "scanned_at": utcnow().isoformat(), "total_bytes": total_bytes, "tables": tables,
            "image_files": image_counts, "image_folders": image_dirs, "other_files": other}


def inventory_text(inv: dict) -> str:
    lines = [f"Export folder: {inv['source']}", f"Total size: {inv['total_bytes'] / 1e9:.2f} GB", ""]
    if inv["image_files"]:
        lines.append("Document images: " + ", ".join(f"{n:,} {ext}" for ext, n in inv["image_files"].items()))
        lines.append("  in folders: " + ", ".join(inv["image_folders"][:5]))
    else:
        lines.append("No document image files were found.")
    lines.append("")
    for t in inv["tables"]:
        if "error" in t:
            lines.append(f"TABLE {t['path']}: could not be read ({t['error']})")
            continue
        lines.append(f"TABLE {t['path']}: {t['rows']:,} rows"
                     + (f", encoding {t.get('encoding')}, delimiter {t.get('delimiter')!r}" if t.get("encoding") else ""))
        for name, c in t["columns"].items():
            date = f"  [dates like {c['looks_like_date']}]" if c.get("looks_like_date") else ""
            lines.append(f"   - {name:30} filled {c['fill_rate'] * 100:5.1f}%   e.g. {', '.join(c['samples'][:3])}{date}")
        lines.append("")
    return "\n".join(lines)


def propose_mapping(inv: dict) -> str:
    """Draft mapping.yaml. Every guess is marked so a person confirms it."""
    tables = [t for t in inv["tables"] if "columns" in t]
    if not tables:
        raise SystemExit("No readable tables were found in the export.")

    def score(t):
        cols = {norm(c) for c in t["columns"]}
        return sum(any(h in cols for h in hints) for hints in HINTS.values()) * 1_000_000 + t["rows"]

    main = max(tables, key=score)
    cols = list(main["columns"])
    ncols = {norm(c): c for c in cols}
    picks: dict[str, str | None] = {}
    for target, hints in HINTS.items():
        picks[target] = next((ncols[h] for h in hints if h in ncols), None)
    layout = "one_row_per_party" if picks["party_name"] and picks["party_role"] and not picks["grantors"] else "one_row_per_document"
    date_fmt = None
    if picks["recorded_date"]:
        date_fmt = main["columns"][picks["recorded_date"]].get("looks_like_date")
    folder = inv["image_folders"][0] if inv["image_folders"] else "images"

    def line(key, value, note=""):
        v = "null" if value is None else json.dumps(value)
        mark = "  # CHECK" if value is not None else "  # not found; fill in if your export has it"
        return f"  {key}: {v}{mark}{(' ' + note) if note else ''}"

    out = [
        "# Records import mapping, drafted automatically from the export.",
        "# Review every line marked CHECK, fix anything wrong, then run:",
        "#   countyctl app migrate records check mapping.yaml",
        "kind: records",
        "source:",
        f"  folder: {json.dumps(inv['source'])}",
        f"  index_file: {json.dumps(main['path'])}  # CHECK: the table with one row per document or per name",
        f"  encoding: {json.dumps(main.get('encoding'))}",
        f"  delimiter: {json.dumps(main.get('delimiter'))}",
        f"layout: {layout}  # one_row_per_document, or one_row_per_party if each row holds one name",
        "columns:",
        line("instrument_number", picks["instrument_number"], "(required)"),
        line("doc_type", picks["doc_type"], "(required)"),
        line("recorded_date", picks["recorded_date"]),
        f"  date_format: {json.dumps(date_fmt)}  # CHECK: Python date format, e.g. \"%m/%d/%Y\"",
        line("book", picks["book"]),
        line("page", picks["page"]),
        line("grantors", picks["grantors"]),
        line("grantees", picks["grantees"]),
        "  name_separator: \";\"  # when one cell holds several names",
        line("party_name", picks["party_name"] if layout == "one_row_per_party" else None),
        line("party_role", picks["party_role"] if layout == "one_row_per_party" else None),
        "  role_values:",
        "    grantor: [\"GRANTOR\", \"GR\", \"FROM\", \"1\", \"G\"]",
        "    grantee: [\"GRANTEE\", \"GE\", \"TO\", \"2\", \"E\"]",
        line("legal_description", picks["legal_description"]),
        line("property_id", picks["property_id"]),
        line("page_count", picks["page_count"]),
        line("remarks", picks["remarks"]),
        line("restricted", picks["restricted"], "(a column that is Y/true for sealed or confidential records)"),
        "doc_type_map: {}  # optional: codes to names, e.g. {WD: Warranty Deed, DT: Deed of Trust}",
        "images:",
        f"  folder: {json.dumps(folder)}  # CHECK: relative to the source folder",
        "  file_name: \"{instrument_number}\"  # CHECK: file name without extension; {instrument_number}, {book}, {page}",
        "  page_suffix: \"\"  # if each page is its own file, e.g. \"_{n}\" or \"-{n:03}\"; leave empty for multi-page files",
        "  search_subfolders: true",
    ]
    return "\n".join(out) + "\n"


@dataclass
class Doc:
    number: str
    doc_type: str
    recorded_date: dt.date | None
    book: str | None
    page: str | None
    grantors: list[str] = field(default_factory=list)
    grantees: list[str] = field(default_factory=list)
    legal: str | None = None
    property_id: str | None = None
    page_count: int | None = None
    remarks: str | None = None
    restricted: bool = False
    source_hash: str = ""
    raw: list[dict] = field(default_factory=list)


def load_mapping(path: Path) -> dict:
    m = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(m, dict) or m.get("kind") != "records":
        raise SystemExit(f"{path} is not a records mapping (it needs 'kind: records').")
    cols = m.get("columns") or {}
    for req in ("instrument_number", "doc_type"):
        if not cols.get(req):
            raise SystemExit(f"mapping.yaml: columns.{req} is required. Set it to the column name in your export.")
    return m


def _split(value: str, sep: str) -> list[str]:
    if not value:
        return []
    parts = [p.strip() for p in (value.split(sep) if sep else [value])]
    return [p for p in parts if p]


def read_docs(m: dict, problems: list[dict]) -> dict[str, Doc]:
    src = Path(m["source"]["folder"])
    cols = m["columns"]
    get = lambda row, key: (row.get(cols[key]) or "").strip() if cols.get(key) else ""  # noqa: E731
    sep = cols.get("name_separator") or ""
    roles = {r: {str(v).upper() for v in vals} for r, vals in (cols.get("role_values") or {}).items()}
    dmap = {str(k).upper(): v for k, v in (m.get("doc_type_map") or {}).items()}
    docs: dict[str, Doc] = {}
    rows = read_rows(src / m["source"]["index_file"], m["source"].get("encoding"), m["source"].get("delimiter"))
    for line_no, row in enumerate(rows, start=2):
        number = get(row, "instrument_number")
        if not number:
            problems.append({"line": line_no, "instrument": "", "problem": "No instrument number"})
            continue
        doc_type_raw = get(row, "doc_type")
        doc_type = dmap.get(doc_type_raw.upper(), doc_type_raw)
        if not doc_type:
            problems.append({"line": line_no, "instrument": number, "problem": "No instrument type"})
            continue
        raw_date = get(row, "recorded_date")
        rdate = parse_date(raw_date, cols.get("date_format")) if raw_date else None
        if raw_date and rdate is None:
            problems.append({"line": line_no, "instrument": number, "problem": f"Unreadable date '{raw_date}'"})
        d = docs.get(number)
        if d is None:
            pc = get(row, "page_count")
            d = Doc(number, doc_type, rdate, get(row, "book") or None, get(row, "page") or None,
                    legal=get(row, "legal_description") or None, property_id=get(row, "property_id") or None,
                    page_count=int(pc) if pc.isdigit() else None, remarks=get(row, "remarks") or None,
                    restricted=get(row, "restricted").upper() in {"Y", "YES", "TRUE", "1", "X"})
            docs[number] = d
        elif m.get("layout") != "one_row_per_party":
            problems.append({"line": line_no, "instrument": number, "problem": "Instrument number appears more than once"})
            continue
        if m.get("layout") == "one_row_per_party":
            name = get(row, "party_name")
            role = get(row, "party_role").upper()
            if name:
                if role in roles.get("grantor", set()):
                    d.grantors.append(name)
                elif role in roles.get("grantee", set()):
                    d.grantees.append(name)
                else:
                    problems.append({"line": line_no, "instrument": number,
                                     "problem": f"Unknown party role '{role}'; add it to role_values"})
            legal = get(row, "legal_description")
            if legal and not d.legal:
                d.legal = legal
        else:
            d.grantors += _split(get(row, "grantors"), sep)
            d.grantees += _split(get(row, "grantees"), sep)
        d.raw.append(row)
    for d in docs.values():
        d.source_hash = hashlib.sha256(json.dumps(d.raw, sort_keys=True).encode()).hexdigest()
    return docs


class ImageFinder:
    def __init__(self, m: dict):
        conf = m.get("images") or {}
        self.root = Path(m["source"]["folder"]) / (conf.get("folder") or "")
        self.pattern = conf.get("file_name") or "{instrument_number}"
        self.page_suffix = conf.get("page_suffix") or ""
        self.index: dict[str, list[Path]] = {}
        if self.root.exists():
            walker = self.root.rglob("*") if conf.get("search_subfolders", True) else self.root.glob("*")
            for p in walker:
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                    self.index.setdefault(p.stem.lower(), []).append(p)

    def find(self, d: Doc) -> list[Path]:
        stem = self.pattern.format(instrument_number=d.number, book=d.book or "", page=d.page or "").lower()
        if not self.page_suffix:
            return sorted(self.index.get(stem, []))
        found = []
        for n in range(1, 2000):
            hits = self.index.get((stem + self.page_suffix.format(n=n)).lower())
            if not hits:
                break
            found.append(sorted(hits)[0])
        return found


def check(m: dict) -> dict:
    problems: list[dict] = []
    docs = read_docs(m, problems)
    finder = ImageFinder(m)
    no_images, pages = 0, 0
    for d in docs.values():
        files = finder.find(d)
        if not files:
            no_images += 1
            continue
        for f in files:
            try:
                pages += 1 if f.suffix.lower() != ".tif" and f.suffix.lower() != ".tiff" else img_mod.frame_count(f)
            except Exception:
                problems.append({"line": "", "instrument": d.number, "problem": f"Image can't be opened: {f.name}"})
    with get_engine().connect() as conn:
        existing = set(conn.execute(select(instruments.c.instrument_number)
                                    .where(instruments.c.instrument_number.in_(list(docs)[:50000]))).scalars()) if docs else set()
    for n in existing:
        problems.append({"line": "", "instrument": n, "problem": "Already in the portal (will be skipped)"})
    return {"documents": len(docs), "image_files_indexed": sum(len(v) for v in finder.index.values()),
            "documents_without_images": no_images, "image_pages_estimated": pages,
            "no_grantor": sum(1 for d in docs.values() if not d.grantors),
            "no_grantee": sum(1 for d in docs.values() if not d.grantees),
            "no_date": sum(1 for d in docs.values() if not d.recorded_date),
            "restricted": sum(1 for d in docs.values() if d.restricted),
            "problems": problems}


def _write_problems(path: Path, problems: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["line", "instrument", "problem"])
        w.writeheader()
        w.writerows(problems)


def load(m: dict, mapping_path: Path, log=print, batch_id: int | None = None) -> int:
    settings = get_settings()
    problems: list[dict] = []
    docs = read_docs(m, problems)
    finder = ImageFinder(m)
    with tx() as conn:
        if batch_id is None:
            batch_id = conn.execute(import_batches.insert().values(kind="records", source=m["source"]["folder"],
                                                                   mapping=m, rows_in=len(docs))
                                    .returning(import_batches.c.id)).scalar_one()
            audit(conn, "migration", "import.start", "import_batch", batch_id, {"documents": len(docs)})
    work = settings.migration_dir / f"batch-{batch_id}"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mapping_path, work / "mapping.yaml")
    with get_engine().connect() as conn:
        already = set(conn.execute(select(instruments.c.instrument_number)).scalars())
    loaded = rejected = 0
    chunk: list[Doc] = list()
    items = [d for d in docs.values() if d.number not in already]
    for n in [d.number for d in docs.values() if d.number in already]:
        problems.append({"line": "", "instrument": n, "problem": "Already in the portal; skipped"})
        rejected += 1

    def flush(batch_docs: list[Doc]) -> None:
        nonlocal loaded, rejected
        with tx() as conn:
            for d in batch_docs:
                files = finder.find(d)
                page_rows = []
                try:
                    seq = 0
                    for f in files:
                        rel_dir = Path(f"batch-{batch_id}") / re.sub(r"[^A-Za-z0-9._-]", "_", d.number)
                        dest_dir = settings.images_dir / rel_dir
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        if f.suffix.lower() == ".pdf":
                            for png in img_mod.pdf_to_pngs(f, dest_dir):
                                seq += 1
                                page_rows.append((seq, png, 0, "image/png"))
                        else:
                            dest = dest_dir / f.name
                            if not dest.exists():
                                shutil.copy2(f, dest)
                            if img_mod.sha256_file(dest) != img_mod.sha256_file(f):
                                raise OSError(f"copy of {f.name} doesn't match the original")
                            frames = img_mod.frame_count(dest) if f.suffix.lower() in (".tif", ".tiff") else 1
                            for frame in range(frames):
                                seq += 1
                                page_rows.append((seq, dest, frame, "image/tiff" if frames > 1 or f.suffix.lower()
                                                  in (".tif", ".tiff") else "image/" + f.suffix.lower().lstrip(".")))
                except Exception as exc:
                    problems.append({"line": "", "instrument": d.number, "problem": f"Image problem: {exc}"})
                    rejected += 1
                    continue
                iid = conn.execute(instruments.insert().values(
                    instrument_number=d.number, doc_type=d.doc_type, recorded_date=d.recorded_date, book=d.book,
                    page=d.page, legal_description=d.legal, property_id=d.property_id,
                    page_count=len(page_rows) or (d.page_count or 0), remarks=d.remarks,
                    status="restricted" if d.restricted else "public", import_batch=batch_id,
                    source_hash=d.source_hash).returning(instruments.c.id)).scalar_one()
                for role, names in (("grantor", d.grantors), ("grantee", d.grantees)):
                    for name in names:
                        conn.execute(parties.insert().values(instrument_id=iid, role=role, name=name,
                                                             name_norm=normalize_name(name)))
                hashes: dict[Path, str] = {}
                for seq, path, frame, mime in page_rows:
                    if path not in hashes:
                        hashes[path] = img_mod.sha256_file(path)
                    conn.execute(images.insert().values(instrument_id=iid, seq=seq,
                                                        path=str(path.relative_to(settings.images_dir)), frame=frame,
                                                        mime=mime, sha256=hashes[path], bytes=path.stat().st_size))
                loaded += 1
            conn.execute(import_batches.update().where(import_batches.c.id == batch_id)
                         .values(rows_loaded=loaded, rows_rejected=rejected))

    for i, d in enumerate(items, start=1):
        chunk.append(d)
        if len(chunk) >= 250:
            flush(chunk)
            chunk = []
            log(f"  {i:,} of {len(items):,} documents processed...")
    if chunk:
        flush(chunk)
    _write_problems(work / "problems.csv", problems)
    with tx() as conn:
        conn.execute(import_batches.update().where(import_batches.c.id == batch_id).values(
            status="loaded", finished_at=utcnow(), rows_loaded=loaded, rows_rejected=rejected))
        audit(conn, "migration", "import.loaded", "import_batch", batch_id, {"loaded": loaded, "rejected": rejected})
    log(f"Batch {batch_id}: {loaded:,} documents loaded, {rejected:,} skipped or rejected.")
    log(f"Problems are listed in {work / 'problems.csv'}")
    return batch_id


def verify(batch_id: int, sample: int = 50, log=print) -> Path:
    settings = get_settings()
    with get_engine().connect() as conn:
        b = conn.execute(select(import_batches).where(import_batches.c.id == batch_id)).mappings().first()
        if b is None or b["kind"] != "records":
            raise SystemExit(f"No records import batch {batch_id}.")
        m = b["mapping"]
        numbers = list(conn.execute(select(instruments.c.instrument_number)
                                    .where(instruments.c.import_batch == batch_id)).scalars())
    problems: list[dict] = []
    source_docs = read_docs(m, problems)
    picked = random.sample(numbers, min(sample, len(numbers)))
    results = []
    from ..records import get as get_record
    with get_engine().connect() as conn:
        for n in sorted(picked):
            r = get_record(conn, n, include_restricted=True)
            s = source_docs.get(n)
            checks = []
            if s is None:
                checks.append(("Source row", False, "not found in the export"))
            else:
                checks.append(("Type", r["doc_type"] == s.doc_type, f"{s.doc_type} / {r['doc_type']}"))
                checks.append(("Recorded date", r["recorded_date"] == s.recorded_date, f"{s.recorded_date} / {r['recorded_date']}"))
                checks.append(("Grantors", sorted(r["grantors"]) == sorted(s.grantors), "; ".join(s.grantors)))
                checks.append(("Grantees", sorted(r["grantees"]) == sorted(s.grantees), "; ".join(s.grantees)))
                checks.append(("Source unchanged", r["source_hash"] == s.source_hash, "row checksum"))
            ok_images = all((settings.images_dir / i["path"]).exists() and
                            img_mod.sha256_file(settings.images_dir / i["path"]) == i["sha256"] for i in r["images"])
            checks.append(("Page images intact", ok_images, f"{len(r['images'])} page(s)"))
            results.append((n, r, checks))
    passed = sum(1 for _, _, c in results if all(ok for _, ok, _ in c))
    rows_html = []
    for n, r, checks in results:
        cells = "".join(f"<li>{'Matches' if ok else '<strong>DIFFERS</strong>'}: {html.escape(name)} "
                        f"<span class='muted'>({html.escape(str(detail))})</span></li>" for name, ok, detail in checks)
        rows_html.append(f"<tr><th scope='row'><a href='{settings.site_url}/staff/records/{html.escape(n)}'>{html.escape(n)}</a></th>"
                         f"<td>{html.escape(r['doc_type'])}</td><td><ul>{cells}</ul></td>"
                         f"<td><label><input type='checkbox'> Clerk checked against the original</label></td></tr>")
    report = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Import batch {batch_id} verification</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:system-ui,sans-serif;max-width:70rem;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#16232E}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #888;padding:.5rem;vertical-align:top;text-align:left}}
.muted{{color:#4A5866}}ul{{margin:0;padding-left:1.2rem}}</style></head><body>
<h1>Import batch {batch_id}: verification report</h1>
<p>Generated {utcnow():%Y-%m-%d %H:%M} UTC. Source: {html.escape(str(m['source']['folder']))}.</p>
<p><strong>{passed} of {len(results)}</strong> randomly chosen documents match the export exactly, including image checksums.
Documents in this batch: {len(numbers):,}.</p>
<h2>How to sign off</h2>
<ol><li>For each row, open the record and compare it with the old system or the paper original.</li>
<li>Tick the box when it matches. Investigate any DIFFERS line before signing off.</li>
<li>In the staff console, go to System, Imports, and sign off batch {batch_id}.</li></ol>
<table><caption>Sample of {len(results)} documents</caption><thead><tr><th scope="col">Instrument</th><th scope="col">Type</th>
<th scope="col">Automatic checks</th><th scope="col">Clerk check</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table>
</body></html>"""
    out = settings.migration_dir / f"batch-{batch_id}" / "verify.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    with tx() as conn:
        conn.execute(import_batches.update().where(import_batches.c.id == batch_id).values(report_path=str(out)))
        audit(conn, "migration", "import.verify", "import_batch", batch_id, {"sample": len(results), "passed": passed})
    log(f"{passed} of {len(results)} sampled documents match. Report: {out}")
    return out


def undo(batch_id: int, log=print) -> None:
    settings = get_settings()
    from .. import ops
    log("Taking a backup before undoing...")
    ops.backup(label=f"before-undo-batch-{batch_id}", log=log)
    with tx() as conn:
        b = conn.execute(select(import_batches).where(import_batches.c.id == batch_id)).mappings().first()
        if b is None:
            raise SystemExit(f"No batch {batch_id}.")
        from ..db import tombstone
        for number in conn.execute(select(instruments.c.instrument_number)
                                   .where(instruments.c.import_batch == batch_id)).scalars():
            tombstone(conn, "instrument", number)
        n = conn.execute(delete(instruments).where(instruments.c.import_batch == batch_id)).rowcount
        conn.execute(import_batches.update().where(import_batches.c.id == batch_id).values(status="undone"))
        audit(conn, "migration", "import.undo", "import_batch", batch_id, {"removed": n})
    shutil.rmtree(settings.images_dir / f"batch-{batch_id}", ignore_errors=True)
    log(f"Batch {batch_id} undone: {n:,} documents removed.")
