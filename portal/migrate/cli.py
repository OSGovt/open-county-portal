"""countyctl app migrate ... : the migration toolkit's commands.

On the server, put export files in /var/lib/county-portal/import/ ; inside
the application they appear at /import/. Every command that writes asks for
confirmation unless you add --yes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..settings import get_settings


def _confirm(msg: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print(f"{msg}\nAdd --yes to confirm when running without a keyboard.")
        return False
    return input(f"{msg} Type yes to continue: ").strip().lower() == "yes"


HOST_DATA = "/var/lib/county-portal/data"
HOST_IMPORT = "/var/lib/county-portal/import"


def _p(path: str | None) -> str | None:
    """Accept the server's paths as well as the container's: on the server the
    folders are /var/lib/county-portal/data and /import is /var/lib/county-portal/import."""
    if not path or Path(path).exists():
        return path
    if path.startswith(HOST_DATA):
        return str(get_settings().data_dir) + path[len(HOST_DATA):]
    if path.startswith(HOST_IMPORT):
        return "/import" + path[len(HOST_IMPORT):]
    return path


def _out(path: str | None, default: str) -> Path:
    p = Path(path) if path else get_settings().migration_dir / default
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def cmd_records(a) -> int:
    a.target = _p(a.target)
    if getattr(a, 'out', None):
        a.out = _p(a.out)
    from . import records as r
    if a.step == "inventory":
        inv = r.inventory(Path(a.target))
        out = _out(a.out, "records-inventory.json")
        out.write_text(json.dumps(inv, indent=1, default=str), encoding="utf-8")
        print(r.inventory_text(inv))
        print(f"\nSaved to {out}. Next: countyctl app migrate records map {a.target}")
        return 0
    if a.step == "map":
        inv = r.inventory(Path(a.target))
        out = _out(a.out, "mapping.yaml")
        if out.exists() and not a.yes:
            print(f"{out} already exists. Add --yes to replace it, or --out to write somewhere else.")
            return 1
        out.write_text(r.propose_mapping(inv), encoding="utf-8")
        print(f"Draft mapping written to {out}")
        print("Open it, check every line marked CHECK, then run: countyctl app migrate records check " + str(out))
        return 0
    m = r.load_mapping(Path(a.target)) if a.step in ("check", "load") else None
    if a.step == "check":
        result = r.check(m)
        print(f"Documents in the export:         {result['documents']:,}")
        print(f"Image files found:               {result['image_files_indexed']:,}")
        print(f"Documents with no image found:   {result['documents_without_images']:,}")
        print(f"Estimated image pages:           {result['image_pages_estimated']:,}")
        print(f"Documents with no grantor:       {result['no_grantor']:,}")
        print(f"Documents with no grantee:       {result['no_grantee']:,}")
        print(f"Documents with no recorded date: {result['no_date']:,}")
        print(f"Marked restricted:               {result['restricted']:,}")
        print(f"Problems:                        {len(result['problems']):,}")
        out = _out(None, "check-problems.csv")
        r._write_problems(out, result["problems"])
        for p in result["problems"][:15]:
            print(f"  line {p['line']}: {p['instrument']} {p['problem']}")
        if len(result["problems"]) > 15:
            print(f"  ...the full list is in {out}")
        print("\nNothing was changed. When the numbers look right: countyctl app migrate records load " + a.target)
        return 0
    if a.step == "load":
        if not _confirm("This imports the documents as a new batch (it can be undone as a whole).", a.yes):
            return 1
        batch = r.load(m, Path(a.target))
        print(f"Next: countyctl app migrate records verify --batch {batch}")
        return 0
    if a.step == "verify":
        if not a.batch:
            print("Add --batch N (the number printed when you loaded).")
            return 1
        r.verify(a.batch, a.sample)
        print("Open the report from the staff console: System, Imports.")
        return 0
    if a.step == "undo":
        if not a.batch:
            print("Add --batch N.")
            return 1
        if not _confirm(f"This removes every document in batch {a.batch}. A backup is taken first.", a.yes):
            return 1
        r.undo(a.batch)
        return 0
    return 1


def cmd_bills(a) -> int:
    a.target = _p(a.target)
    if a.step != "undo" and not a.target:
        print("Give the export file (map) or the mapping file (check, load).")
        return 1
    if getattr(a, 'out', None):
        a.out = _p(a.out)
    from . import bills as b
    if a.step == "map":
        if not a.kind or not a.office:
            print("Add --kind (property_tax, court, utility, permit, other) and --office (for example tax-office).")
            return 1
        out = _out(a.out, f"bills-{a.kind}.yaml")
        out.write_text(b.propose_mapping(Path(a.target), a.kind, a.office), encoding="utf-8")
        print(f"Draft written to {out}. Check it, then: countyctl app migrate bills check {out}")
        return 0
    if a.step == "check":
        res = b.check(Path(a.target))
        print(f"Rows: {res['rows']:,}  Accounts: {res['accounts']:,}  Total due: ${res['total_due_cents'] / 100:,.2f}")
        for p in res["problems"][:20]:
            print("  " + p)
        if len(res["problems"]) > 20:
            print(f"  ...and {len(res['problems']) - 20} more")
        print("Nothing was changed.")
        return 0
    if a.step == "load":
        b.load(Path(a.target), force=a.force)
        return 0
    if a.step == "undo":
        if not a.batch:
            print("Add --batch N (the number shown when the bills were loaded; also in System > Imports).")
            return 1
        b.undo(a.batch)
        return 0
    return 1


def cmd_site(a) -> int:
    a.target = _p(a.target)
    if getattr(a, 'out', None):
        a.out = _p(a.out)
    from . import site as s
    if a.step == "crawl":
        if not a.target:
            print("Give the old site's address, for example https://www.example-county.gov")
            return 1
        s.crawl(a.target, a.max_pages, a.delay, a.ignore_robots)
        print("Next: countyctl app migrate site import")
        return 0
    if a.step == "import":
        s.import_site()
        print("Review the imported pages in the staff console: Content, 'Pages waiting for review'.")
        return 0
    return 1


def register(sub) -> None:
    mig = sub.add_parser("migrate", help="Move records, bills and old website content into the portal.")
    msub = mig.add_subparsers(dest="area", required=True)

    rp = msub.add_parser("records", help="Recorded documents and their images.")
    rp.add_argument("step", choices=["inventory", "map", "check", "load", "verify", "undo"])
    rp.add_argument("target", nargs="?", help="Export folder (inventory, map) or mapping file (check, load)")
    rp.add_argument("--out")
    rp.add_argument("--batch", type=int)
    rp.add_argument("--sample", type=int, default=50)
    rp.add_argument("--yes", action="store_true")
    rp.set_defaults(fn=cmd_records)

    bp = msub.add_parser("bills", help="Tax roll, court costs, utility accounts.")
    bp.add_argument("step", choices=["map", "check", "load", "undo"])
    bp.add_argument("target", nargs="?", help="Export file (map) or mapping file (check, load)")
    bp.add_argument("--batch", type=int, help="Batch number (undo)")
    bp.add_argument("--force", action="store_true", help="Load even if many accounts would be set to $0")
    bp.add_argument("--kind")
    bp.add_argument("--office")
    bp.add_argument("--out")
    bp.set_defaults(fn=cmd_bills)

    sp = msub.add_parser("site", help="Pages and documents from the old website.")
    sp.add_argument("step", choices=["crawl", "import"])
    sp.add_argument("target", nargs="?", help="Old site address (crawl)")
    sp.add_argument("--max-pages", type=int, default=3000)
    sp.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (be gentle with the old server)")
    sp.add_argument("--ignore-robots", action="store_true", help="Your own site may block crawlers; use with permission")
    sp.set_defaults(fn=cmd_site)
