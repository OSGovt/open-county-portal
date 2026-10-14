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


def load(path: Path, log=print) -> int:
    m = _load_mapping(path)
    kind, office = m["bill_kind"], m["office"]
    added = updated = zeroed = skipped = 0
    with tx() as conn:
        batch = conn.execute(import_batches.insert().values(kind=f"bills:{kind}", source=m["source"]["file"], mapping=m)
                             .returning(import_batches.c.id)).scalar_one()
        existing = {r.account: r.id for r in conn.execute(select(receivables.c.account, receivables.c.id)
                                                           .where(receivables.c.kind == kind))}
        seen = set()
        for _, r in _rows(m):
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
    log(f"Bills ({kind}): {added:,} added, {updated:,} updated, {zeroed:,} set to $0, {skipped:,} skipped.")
    return batch
