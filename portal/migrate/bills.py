"""Bill import: property tax roll, court costs, utility accounts.

Run it whenever the billing system produces a fresh export (nightly is
typical). Accounts are matched by number: new ones are added, existing ones
updated. With sync: true, accounts missing from the file are set to $0 due,
because they were paid or closed in the billing system.

Payments taken in the portal are exported for posting back into the billing
system from Finance, "Download bill payments to post".
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select

from ..db import audit, import_batches, receivables, tx, utcnow
from ..web import parse_money
from .tabular import norm, parse_date, profile, read_rows

KINDS = {"property_tax", "court", "utility", "permit", "other"}
HINTS = {
    "account": ["account", "accountnumber", "acct", "acctno", "accountno", "casenumber", "case", "citation", "propid"],
    "name": ["name", "owner", "ownername", "defendant", "customer", "taxpayer"],
    "address": ["address", "situs", "situsaddress", "serviceaddress", "propertyaddress", "location"],
    "amount_due": ["amountdue", "totaldue", "balance", "balancedue", "due", "amount", "total"],
    "due_date": ["duedate", "due", "delinquentdate"],
    "description": ["description", "desc", "taxyear", "year"],
}


def propose_mapping(file: Path, kind: str, office: str) -> str:
    info = profile(file)
    cols = {norm(c): c for c in info["columns"]}
    pick = {k: next((cols[h] for h in hints if h in cols), None) for k, hints in HINTS.items()}
    lines = ["# Bill import mapping. Check each column, then run:",
             "#   countyctl app migrate bills check bills.yaml",
             "kind: bills", f"bill_kind: {kind}  # property_tax, court, utility, permit or other",
             f"office: {office}  # the office that collects these bills", "source:",
             f"  file: \"{file.resolve()}\"", f"  encoding: \"{info.get('encoding') or ''}\"",
             f"  delimiter: \"{info.get('delimiter') or ''}\"", "columns:"]
    import json
    for k, v in pick.items():
        shown = json.dumps(v) if v else "null"
        lines.append(f"  {k}: {shown}  # {'CHECK' if v else 'not found'}")
    lines += ["amount_in_cents: false  # true if amounts are whole cents, like 21843 for $218.43",
              "allow_partial: true", "sync: true  # set accounts not in this file to $0 due"]
    return "\n".join(lines) + "\n"


def _load_mapping(path: Path) -> dict:
    m = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(m, dict) or m.get("kind") != "bills":
        raise SystemExit(f"{path} is not a bills mapping (it needs 'kind: bills').")
    if m.get("bill_kind") not in KINDS:
        raise SystemExit(f"bill_kind must be one of: {', '.join(sorted(KINDS))}")
    for req in ("account", "amount_due"):
        if not (m.get("columns") or {}).get(req):
            raise SystemExit(f"columns.{req} is required.")
    return m


def _rows(m: dict):
    cols = m["columns"]
    src = m["source"]
    for line_no, row in enumerate(read_rows(Path(src["file"]), src.get("encoding") or None, src.get("delimiter") or None), 2):
        get = lambda k: (row.get(cols[k]) or "").strip() if cols.get(k) else ""  # noqa: E731
        account = get("account")
        raw_amt = get("amount_due")
        if m.get("amount_in_cents"):
            amount = int(raw_amt) if raw_amt.lstrip("-").isdigit() else None
        else:
            amount = parse_money(raw_amt.replace("(", "-").replace(")", "")) if raw_amt else None
        yield line_no, {"account": account, "name": get("name") or None, "address": get("address") or None,
                        "amount": amount, "due_date": parse_date(get("due_date")) if get("due_date") else None,
                        "description": get("description") or None, "raw_amount": raw_amt}


def check(path: Path) -> dict:
    m = _load_mapping(path)
    problems, n, total = [], 0, 0
    seen = set()
    for line_no, r in _rows(m):
        n += 1
        if not r["account"]:
            problems.append(f"line {line_no}: no account number")
        elif r["account"] in seen:
            problems.append(f"line {line_no}: account {r['account']} appears twice")
        seen.add(r["account"])
        if r["amount"] is None:
            problems.append(f"line {line_no}: amount '{r['raw_amount']}' isn't a number")
        else:
            total += r["amount"]
    return {"rows": n, "accounts": len(seen), "total_due_cents": total, "problems": problems}


SNAP_COLS = ("account", "office_slug", "name", "address", "amount_due_cents", "due_date", "description",
             "allow_partial", "import_batch")
MAX_DROP = 0.2  # refuse a sync that would zero more than 20% of accounts unless forced


def _snapshot_path(batch: int) -> Path:
    from ..settings import get_settings
    d = get_settings().migration_dir / "bills-undo"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"batch-{batch}.json"


def load(path: Path, log=print, force: bool = False) -> int:
    import json
    m = _load_mapping(path)
    kind, office = m["bill_kind"], m["office"]
    added = updated = zeroed = skipped = 0
    rows = [r for _, r in _rows(m)]
    with tx() as conn:
        current = [dict(r) for r in conn.execute(select(*[receivables.c[c] for c in SNAP_COLS])
                                                 .where(receivables.c.kind == kind)).mappings()]
        incoming = {r["account"] for r in rows if r["account"] and r["amount"] is not None}
        if m.get("sync") and not force and len(current) >= 20:
            missing = sum(1 for c in current if c["account"] not in incoming and c["amount_due_cents"])
            if missing > MAX_DROP * len(current):
                raise SystemExit(
                    f"Stopped: this file would set {missing:,} of {len(current):,} {kind} accounts to $0. That usually "
                    "means the export was cut short or is the wrong file. Nothing was changed. If it's right, run the "
                    "same command again with --force.")
        batch = conn.execute(import_batches.insert().values(kind=f"bills:{kind}", source=m["source"]["file"], mapping=m)
                             .returning(import_batches.c.id)).scalar_one()
        # Everything this load can change is saved first, so 'migrate bills undo' can put it back.
        _snapshot_path(batch).write_text(json.dumps({"kind": kind, "rows": current}, default=str), encoding="utf-8")
        existing = {r.account: r.id for r in conn.execute(select(receivables.c.account, receivables.c.id)
                                                           .where(receivables.c.kind == kind))}
        seen = set()
        for r in rows:
            if not r["account"] or r["amount"] is None or r["account"] in seen:
                skipped += 1
                continue
            seen.add(r["account"])
            values = {"office_slug": office, "name": r["name"], "address": r["address"],
                      "amount_due_cents": max(0, r["amount"]), "due_date": r["due_date"],
                      "description": r["description"], "allow_partial": bool(m.get("allow_partial", True)),
                      "import_batch": batch, "updated_at": utcnow()}
            if r["account"] in existing:
                conn.execute(receivables.update().where(receivables.c.id == existing[r["account"]]).values(**values))
                updated += 1
            else:
                conn.execute(receivables.insert().values(kind=kind, account=r["account"], **values))
                added += 1
        if m.get("sync"):
            for account, rid in existing.items():
                if account not in seen:
                    conn.execute(receivables.update().where(receivables.c.id == rid)
                                 .values(amount_due_cents=0, updated_at=utcnow()))
                    zeroed += 1
        conn.execute(import_batches.update().where(import_batches.c.id == batch).values(
            status="verified", finished_at=utcnow(), rows_in=added + updated + skipped, rows_loaded=added + updated,
            rows_rejected=skipped, signed_off_by="automatic (bill sync)"))
        audit(conn, "migration", "bills.load", "import_batch", batch,
              {"kind": kind, "added": added, "updated": updated, "zeroed": zeroed, "skipped": skipped})
    log(f"Batch {batch}. Bills ({kind}): {added:,} added, {updated:,} updated, {zeroed:,} set to $0, {skipped:,} skipped.")
    log(f"To undo: countyctl app migrate bills undo --batch {batch}")
    return batch


def undo(batch: int, log=print) -> None:
    """Put a kind's bills back exactly as they were before batch N. Only the
    latest load of that kind can be undone (later loads build on it)."""
    import datetime as _dt
    import json
    snap = _snapshot_path(batch)
    if not snap.exists():
        raise SystemExit(f"No saved state for batch {batch}; it can't be undone.")
    data = json.loads(snap.read_text(encoding="utf-8"))
    kind = data["kind"]
    with tx() as conn:
        latest = conn.execute(select(import_batches.c.id).where(import_batches.c.kind == f"bills:{kind}",
                                                                import_batches.c.status != "undone")
                              .order_by(import_batches.c.id.desc())).scalar()
        if latest != batch:
            raise SystemExit(f"Batch {batch} isn't the latest {kind} load (that's batch {latest}). Undo that one first.")
        before = {r["account"]: r for r in data["rows"]}
        gone = receivables.delete().where(receivables.c.kind == kind)
        if before:
            gone = gone.where(receivables.c.account.notin_(list(before)))
        conn.execute(gone)  # accounts the undone load added
        for account, r in before.items():
            values = {k: r[k] for k in SNAP_COLS if k != "account"}
            if values.get("due_date"):
                values["due_date"] = _dt.date.fromisoformat(str(values["due_date"])[:10])
            values["updated_at"] = utcnow()
            n = conn.execute(receivables.update().where(receivables.c.kind == kind, receivables.c.account == account)
                             .values(**values)).rowcount
            if not n:
                conn.execute(receivables.insert().values(kind=kind, account=account, **values))
        conn.execute(import_batches.update().where(import_batches.c.id == batch).values(status="undone"))
        audit(conn, "migration", "bills.undo", "import_batch", batch, {"kind": kind, "accounts": len(before)})
    log(f"Batch {batch} undone: {kind} bills are back to how they were before it ({len(before):,} accounts).")
