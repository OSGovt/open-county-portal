"""Generate a fictional county's records.

The model: land is divided into parcels (subdivision lots and acreage tracts).
Each parcel gets a history from its first recorded document to today: sales
(warranty deed, usually with a deed of trust to a lender), refinances, payoffs
(releases of lien), occasional liens, judgments, easements and heirship
affidavits, and plats when subdivisions are created. Names come with realistic
frequency (see names.json for the source lists). All of it is fictional, every
page says so, and a fixed seed always produces the same county.

Fake Social Security numbers, used to demonstrate the redaction scan, always
have 00 as their middle two digits: the Social Security Administration has
never issued such a number, so none can belong to a real person.
"""
from __future__ import annotations

import bisect
import datetime as dt
import io
import itertools
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, text

from ..db import get_engine, images, import_batches, instruments, meetings, parties, postings, receivables, tx, utcnow
from ..records import normalize_name
from .pages import SYNTHETIC_DIR

HERE = Path(__file__).parent
DEMO_BATCH_SOURCE = "demo-sample-data"

SUB_FIRST = ["Serenity", "Harmony", "Tranquil", "Golden", "Willow", "Cedar", "Bluebonnet", "Meadow", "Quail", "Lantern",
             "Juniper", "Silver", "Copper", "Kestrel", "Prairie", "Amber", "Heron", "Laurel", "Mesquite", "Sable",
             "Haven", "Lark", "Morning", "Stone", "Clover", "Indigo", "Briar", "Fox", "Maple", "Aspen"]
SUB_SECOND = ["Ridge", "Hills", "Creek", "Crossing", "Meadows", "Park", "Oaks", "Springs", "Hollow", "Trails",
              "Landing", "Estates", "Heights", "Bend", "Point", "Village", "Glen", "Grove", "Vista", "Ranch"]
STREETS = ["Calm", "Bliss", "Harmony", "Content", "Gentle", "Morningstar", "Stillwater", "Kindness", "Patience", "Lumen",
           "Halcyon", "Placid", "Concord", "Amity", "Mercy", "Grace", "Hope", "Unity", "Pleasant", "Quiet"]
STREET_TYPES = ["Lane", "Way", "Drive", "Court", "Road", "Trail", "Path", "Circle", "Loop", "Street"]
SURVEYS = ["Placid Valley", "Elysian Grant", "Arcadia", "Shangri", "Halcyon", "Eden Fork", "Avalon", "Calm Water"]
BANKS = ["UTOPIA FIRST NATIONAL BANK", "NIRVANA FEDERAL CREDIT UNION", "SERENITY SAVINGS BANK", "HARMONY HOME LOANS LLC",
         "TRANQUIL MORTGAGE COMPANY", "BLISS COUNTY STATE BANK", "CONCORD LENDING GROUP INC", "PLACID VALLEY BANK"]
CREDITORS = ["UTOPIA SUPPLY CO", "HALCYON ROOFING LLC", "STILLWATER PLUMBING INC", "AMITY LUMBER COMPANY"]
DOC_PAGES = {"Warranty Deed": (2, 4), "Deed of Trust": (4, 9), "Release of Lien": (1, 2), "Plat": (1, 3),
             "Mechanic's Lien": (1, 2), "Abstract of Judgment": (1, 2), "Easement": (2, 4),
             "Affidavit of Heirship": (2, 3), "Special Warranty Deed": (2, 3), "Tax Lien": (1, 1)}


@dataclass
class Parcel:
    pid: str
    legal: str
    address: str
    created: dt.date
    owners: list[str] = field(default_factory=list)
    lender: str | None = None
    lien_doc: str | None = None
    value: int = 0


class Names:
    def __init__(self, rng: random.Random) -> None:
        data = json.loads((HERE / "names.json").read_text(encoding="utf-8"))
        self.rng = rng
        self.first = data["first_female"] + data["first_male"]
        self.last = data["last"]
        self._fw = list(itertools.accumulate(w for _, w in self.first))
        self._lw = list(itertools.accumulate(w for _, w in self.last))

    def _pick(self, items, cum) -> str:
        return items[bisect.bisect(cum, self.rng.random() * cum[-1])][0]

    def person(self, last: str | None = None) -> str:
        last = last or self._pick(self.last, self._lw)
        initial = chr(self.rng.randint(65, 90)) if self.rng.random() < 0.6 else ""
        return " ".join(p for p in (last.upper(), self._pick(self.first, self._fw).upper(), initial) if p)

    def household(self) -> list[str]:
        a = self.person()
        if self.rng.random() < 0.55:  # a couple sharing a surname
            return [a, self.person(a.split()[0])]
        return [a]

    def company(self) -> str:
        kind = self.rng.choice(["HOLDINGS LLC", "PROPERTIES LLC", "LAND COMPANY", "INVESTMENTS LP", "FAMILY TRUST"])
        return f"{self._pick(self.last, self._lw).upper()} {kind}"


def _fake_ssn(rng: random.Random) -> str:
    area = rng.randint(1, 899)
    while area == 666:
        area = rng.randint(1, 899)
    return f"{area:03d}-00-{rng.randint(1, 9999):04d}"


def generate(scale: int = 200_000, seed: int = 7, start_year: int = 1985, log=print) -> int:
    rng = random.Random(seed)
    names = Names(rng)
    today = dt.date.today()
    span = (today - dt.date(start_year, 1, 1)).days
    docs: list[tuple] = []        # (number, type, date, grantors, grantees, legal, pid, remarks, ssn)
    parcels: list[Parcel] = []
    counters: dict[int, itertools.count] = {}

    def number_for(d: dt.date) -> str:
        c = counters.setdefault(d.year, itertools.count(1))
        return f"{d.year}-{next(c):06d}"

    def rand_date(after: dt.date, max_days: int) -> dt.date:
        return after + dt.timedelta(days=rng.randint(30, max(31, max_days)))

    def add(dtype, date, grantors, grantees, parcel: Parcel | None, legal=None, remarks=None):
        date = min(date, today)  # follow-on documents (releases) never land in the future
        ssn = _fake_ssn(rng) if rng.random() < 1 / 20_000 else None
        docs.append([None, dtype, date, grantors, grantees, legal or (parcel.legal if parcel else ""),
                     parcel.pid if parcel else None, remarks, ssn])
        return len(docs) - 1

    log(f"Planning about {scale:,} documents (seed {seed})...")
    pid_seq = itertools.count(100001)
    sub_names = iter(f"{a} {b}" for a, b in rng.sample(list(itertools.product(SUB_FIRST, SUB_SECOND)),
                                                        len(SUB_FIRST) * len(SUB_SECOND)))
    while len(docs) < scale:
        # A new subdivision (most land) or a few acreage tracts.
        created = dt.date(start_year, 1, 1) + dt.timedelta(days=rng.randint(0, int(span * 0.85)))
        if rng.random() < 0.8:
            sub = next(sub_names, None) or f"{rng.choice(SUB_FIRST)} {rng.choice(SUB_SECOND)} Section {rng.randint(2, 9)}"
            developer = names.company()
            lots = rng.randint(12, 120)
            add("Plat", created, [developer], ["THE PUBLIC"], None,
                legal=f"{sub.upper()}, LOTS 1-{lots}", remarks=f"{lots} lots")
            for lot in range(1, lots + 1):
                block = (lot - 1) // 12 + 1
                street = f"{rng.choice(STREETS)} {rng.choice(STREET_TYPES)}"
                parcels.append(Parcel(f"R{next(pid_seq)}", f"{sub.upper()}, LOT {lot}, BLOCK {block}",
                                      f"{rng.randint(100, 9999)} {street}", created, [developer],
                                      value=rng.randint(160, 520) * 1000))
        else:
            for _ in range(rng.randint(1, 4)):
                acres = round(rng.uniform(2, 240), 2)
                survey = rng.choice(SURVEYS)
                parcels.append(Parcel(f"R{next(pid_seq)}",
                                      f"{acres} ACRES, {survey.upper()} SURVEY, ABSTRACT {rng.randint(1, 900)}",
                                      f"{rng.randint(1000, 19999)} County Road {rng.randint(100, 499)}", created,
                                      names.household(), value=int(acres * rng.randint(4, 15) * 1000)))
        # Histories for every parcel not yet given one.
        for p in parcels:
            if getattr(p, "_done", False):
                continue
            p._done = True  # type: ignore[attr-defined]
            d = p.created
            while len(docs) < scale:
                d = rand_date(d, 365 * 7)
                if d > today:
                    break
                roll = rng.random()
                if roll < 0.45:  # a sale
                    buyers = names.household() if rng.random() > 0.08 else [names.company()]
                    kind = "Warranty Deed" if rng.random() > 0.12 else "Special Warranty Deed"
                    add(kind, d, p.owners, buyers, p)
                    if p.lien_doc and rng.random() < 0.9:  # seller's loan paid off at closing
                        add("Release of Lien", d + dt.timedelta(days=rng.randint(5, 60)), [p.lender], p.owners, p,
                            remarks=p.lien_doc)
                        p.lender = p.lien_doc = None
                    p.owners = buyers
                    if rng.random() < 0.75:
                        p.lender = rng.choice(BANKS)
                        i = add("Deed of Trust", d, buyers, [p.lender], p)
                        p.lien_doc = docs[i]  # resolved to a number below
                elif roll < 0.65 and p.lien_doc:  # refinance or payoff
                    if rng.random() < 0.5:
                        new_lender = rng.choice(BANKS)
                        i = add("Deed of Trust", d, p.owners, [new_lender], p)
                        add("Release of Lien", d + dt.timedelta(days=rng.randint(10, 90)), [p.lender], p.owners, p,
                            remarks=p.lien_doc)
                        p.lender, p.lien_doc = new_lender, docs[i]
                    else:
                        add("Release of Lien", d, [p.lender], p.owners, p, remarks=p.lien_doc)
                        p.lender = p.lien_doc = None
                elif roll < 0.72:
                    add("Mechanic's Lien", d, [rng.choice(CREDITORS)], p.owners, p)
                elif roll < 0.77:
                    add("Abstract of Judgment", d, [names.company() if rng.random() < .5 else names.person()],
                        p.owners, p)
                elif roll < 0.84:
                    add("Easement", d, p.owners, [rng.choice(["UTOPIA ELECTRIC COOPERATIVE",
                                                              "NIRVANA WATER SUPPLY CORPORATION",
                                                              "UTOPIA COUNTY"])], p)
                elif roll < 0.88:
                    heirs = names.household()
                    add("Affidavit of Heirship", d, p.owners[:1], heirs, p)
                    p.owners = heirs
                elif roll < 0.9:
                    add("Tax Lien", d, ["UTOPIA COUNTY TAX ASSESSOR-COLLECTOR"], p.owners, p)
            if len(docs) >= scale:
                break

    docs = docs[:scale]
    docs.sort(key=lambda r: r[2])
    for r in docs:
        r[0] = number_for(r[2])
    for r in docs:  # a release's remarks name the deed of trust it releases
        if isinstance(r[7], list):
            r[7] = f"Releases deed of trust {r[7][0]}" if r[7][0] else "Releases a prior deed of trust"
    log(f"Planned {len(docs):,} documents on {len(parcels):,} parcels. Loading...")
    return _load(docs, parcels, rng, log)


def _copy(cur, table: str, columns: list[str], rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def _load(docs, parcels, rng: random.Random, log) -> int:
    engine = get_engine()
    with tx() as conn:
        if conn.execute(select(import_batches.c.id).where(import_batches.c.source == DEMO_BATCH_SOURCE,
                                                          import_batches.c.status != "undone")).first():
            raise SystemExit("Sample data is already loaded. Remove it first: countyctl app demo --remove")
        batch = conn.execute(import_batches.insert().values(kind="demo", source=DEMO_BATCH_SOURCE, status="loading")
                             .returning(import_batches.c.id)).scalar_one()
        first_id = (conn.execute(select(func.max(instruments.c.id))).scalar() or 0) + 1
    now = utcnow()
    raw = engine.raw_connection()
    try:
        cur = raw.driver_connection.cursor()
        cur.execute("DROP INDEX IF EXISTS ix_parties_name_trgm")
        cur.execute("DROP INDEX IF EXISTS ix_instruments_legal_trgm")
        inst_rows, party_rows, image_rows = [], [], []
        for k, (number, dtype, date, grantors, grantees, legal, pid, remarks, ssn) in enumerate(docs):
            iid = first_id + k
            lo, hi = DOC_PAGES[dtype]
            pages = rng.randint(lo, hi)
            restricted = rng.random() < 0.0005
            inst_rows.append((iid, number, dtype, date, legal, pid, pages, remarks,
                              "restricted" if restricted else "public", batch, now))
            for role, people in (("grantor", grantors), ("grantee", grantees)):
                for name in people:
                    if name:
                        party_rows.append((iid, role, name, normalize_name(name)))
            page1 = [dtype.upper(), f"Instrument number {number}", f"Recorded {date:%B %d, %Y}",
                     f"Grantor: {'; '.join(g for g in grantors if g)}", f"Grantee: {'; '.join(grantees)}"]
            if legal:
                page1.append(f"Legal description: {legal}")
            if remarks:
                page1.append(f"Remarks: {remarks}")
            if ssn:
                page1.append(f"Grantor SSN: {ssn}")
            page1.append("Utopia County, Nirvana is fictional. This document was generated for a demonstration.")
            for seq in range(1, pages + 1):
                txt = "\n".join(page1) if seq == 1 else f"{dtype.upper()} {number}\nPage {seq} of {pages}"
                image_rows.append((iid, seq, f"{SYNTHETIC_DIR}/{number}/{seq}", 0, "image/png", "", txt, False, now))
        log(f"  instruments: {_copy(cur, 'instruments', ['id', 'instrument_number', 'doc_type', 'recorded_date', 'legal_description', 'property_id', 'page_count', 'remarks', 'status', 'import_batch', 'updated_at'], inst_rows):,}")
        log(f"  names:       {_copy(cur, 'parties', ['instrument_id', 'role', 'name', 'name_norm'], party_rows):,}")
        log(f"  page images: {_copy(cur, 'images', ['instrument_id', 'seq', 'path', 'frame', 'mime', 'sha256', 'ocr_text', 'redacted', 'updated_at'], image_rows):,} (drawn when viewed; nothing stored)")
        cur.execute("SELECT setval(pg_get_serial_sequence('instruments', 'id'), (SELECT max(id) FROM instruments))")
        raw.commit()
    except BaseException:
        raw.rollback()
        with tx() as conn:  # nothing was loaded; let the next attempt start clean
            conn.execute(import_batches.update().where(import_batches.c.id == batch).values(status="undone"))
        raise
    finally:
        raw.close()
    log("  rebuilding search indexes...")
    with tx() as conn:
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_parties_name_trgm ON parties USING gin (name_norm gin_trgm_ops)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_instruments_legal_trgm ON instruments USING gin (legal_description gin_trgm_ops)"))
        except Exception as exc:  # pg_trgm unavailable: search still works, more slowly
            log(f"  (fast-search index not available: {exc.__class__.__name__})")
    with tx() as conn:
        n_bills = _bills(conn, parcels, docs, batch, rng)
        n_meet = _meetings(conn, rng)
        n_post = _postings(conn)
        conn.execute(import_batches.update().where(import_batches.c.id == batch).values(
            status="loaded", finished_at=utcnow(), rows_in=len(docs), rows_loaded=len(docs), rows_rejected=0))
    with get_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for t in ("instruments", "parties", "images", "receivables"):
            conn.execute(text(f"ANALYZE {t}"))
    log(f"  bills: {n_bills:,}, meetings: {n_meet}, notices: {n_post}")
    return batch


def _bills(conn, parcels, docs, batch, rng) -> int:
    owners: dict[str, list[str]] = {}
    for r in docs:  # latest grantee of a conveyance is the current owner
        if r[6] and r[1] in ("Warranty Deed", "Special Warranty Deed", "Affidavit of Heirship"):
            owners[r[6]] = r[4]
    rows = []
    people = Names(rng)
    due = dt.date(dt.date.today().year + 1, 1, 31)
    for p in parcels:
        if p.pid not in owners or rng.random() < 0.55:  # most taxes are already paid
            continue
        tax = int(p.value * rng.uniform(0.017, 0.024) * 100)
        if rng.random() < 0.3:
            tax = int(tax * rng.uniform(0.2, 0.8))  # partly paid
        rows.append(dict(kind="property_tax", office_slug=_office(conn, "tax"), account=p.pid,
                         name="; ".join(owners[p.pid]), address=p.address, amount_due_cents=tax, due_date=due,
                         description=f"{dt.date.today().year} property tax (sample)", allow_partial=True,
                         import_batch=batch, updated_at=utcnow()))
    for i in range(max(10, len(parcels) // 40)):
        rows.append(dict(kind="court", office_slug=_office(conn, "district"), account=f"CR-{rng.randint(15, 26)}-{i:05d}",
                         name=people.person(), address="", amount_due_cents=rng.randint(80, 900) * 100,
                         due_date=due, description="Court costs and fines (sample)", allow_partial=True,
                         import_batch=batch, updated_at=utcnow()))
    for chunk in range(0, len(rows), 5000):
        conn.execute(receivables.insert(), rows[chunk:chunk + 5000])
    return len(rows)


_office_cache: dict[str, str] = {}


def _office(conn, hint: str) -> str:
    if hint not in _office_cache:
        from ..db import offices
        slugs = list(conn.execute(select(offices.c.slug)).scalars())
        _office_cache[hint] = next((s for s in slugs if hint in s), slugs[0] if slugs else "main-office")
    return _office_cache[hint]


def _meetings(conn, rng) -> int:
    today = dt.date.today()
    rows = []
    d = today - dt.timedelta(days=730)
    while d < today + dt.timedelta(days=60):
        if d.weekday() == 1 and (d.day - 1) // 7 in (1, 3):  # second and fourth Tuesdays
            starts = dt.datetime.combine(d, dt.time(15, 0), dt.timezone.utc)
            past = d < today
            items = rng.sample(["Consider bills and payroll", "Road and bridge report", "Burn ban status",
                                "Consider plat of a new subdivision", "Budget workshop", "Public hearing on tax rate",
                                "Consider interlocal agreement with the City of Serenity", "Personnel matters",
                                "Consider bids for courthouse roof", "Proclamations"], 5)
            agenda = "\n".join(f"{i}. {t}" for i, t in enumerate(["Call to order", "Public comment"] + items +
                                                                  ["Adjourn"], 1))
            rows.append(dict(body="Commissioners Court", title=f"SAMPLE: Regular meeting, {d:%B %d, %Y}",
                             starts_at=starts, location="Utopia County Courthouse, 1 Harmony Square",
                             status="held" if past else "posted", posted_at=starts - dt.timedelta(days=4),
                             agenda=agenda,
                             minutes=("All items considered; see the agenda. (Sample minutes.)" if past else None)))
        d += dt.timedelta(days=1)
    conn.execute(meetings.insert(), rows)
    return len(rows)


def _postings(conn) -> int:
    from .. import config_store, statepacks
    site = config_store.get(conn, "site")
    try:
        rules = statepacks.posting_rules(site["state"], site["jurisdiction_type"])
    except statepacks.PackError:
        rules = []
    n = 0
    for rule in rules:
        if rule.get("automatic") or rule["cadence"] == "per_meeting":
            continue
        conn.execute(postings.insert().values(rule_code=rule["code"], title=f"SAMPLE: {rule['title']}",
                                              body="Sample notice for the demonstration county.", published=True))
        n += 1
    return n
