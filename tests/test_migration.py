"""Migration toolkit: a realistic messy export goes through every step."""
from __future__ import annotations

import io
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from PIL import Image
from sqlalchemy import select

import pytest

from portal import cli
from portal.db import import_batches, instruments, pages, receivables, redirects, tx


@pytest.fixture(autouse=True, scope="module")
def _fresh_sample_data():
    """These tests replace the tax roll; put the sample data back for the test files that follow."""
    yield
    cli.main(["demo", "--remove"])
    cli.main(["demo"])


def _make_export(root: Path) -> Path:
    """An export like an old vendor's: cp1252 CSV, US dates, one row per party, multi-page TIFFs."""
    exp = root / "export"
    (exp / "IMAGES" / "2019").mkdir(parents=True)
    rows = ["InstNum,DocType,RecDate,Vol,Pg,Name,PartyType,LegalDesc,PropID",
            "1999-000123,WD,03/14/1999,412,77,SMITH JOHN,GR,LOT 4 BLK 2 OAK HILLS,R1001",
            "1999-000123,WD,03/14/1999,412,77,DOE JANE,GE,LOT 4 BLK 2 OAK HILLS,R1001",
            "1999-000124,DT,03/14/1999,412,80,DOE JANE,GR,LOT 4 BLK 2 OAK HILLS,R1001",
            "1999-000124,DT,03/14/1999,412,80,FIRST STATE BANK,GE,LOT 4 BLK 2 OAK HILLS,R1001",
            "2001-004455,REL,7/2/2001,,,FIRST STATE BANK,GR,LOT 4 BLK 2 OAK HILLS,",
            "2001-004455,REL,7/2/2001,,,DOE JANE,GE,LOT 4 BLK 2 OAK HILLS,",
            "2002-000001,WD,13/45/2002,,,MUÑOZ ROSA,GR,CAFÉ TRACT,"]
    (exp / "index.csv").write_bytes(("\r\n".join(rows) + "\r\n").encode("cp1252"))
    for number, pages_ in (("1999-000123", 2), ("1999-000124", 3), ("2001-004455", 1)):
        frames = [Image.new("L", (850, 1100), 255) for _ in range(pages_)]
        frames[0].save(exp / "IMAGES" / "2019" / f"{number}.tif", save_all=True, append_images=frames[1:],
                       compression="tiff_deflate")
    return exp


def test_records_migration_end_to_end(tmp_path, capsys):
    exp = _make_export(tmp_path)
    assert cli.main(["migrate", "records", "inventory", str(exp), "--out", str(tmp_path / "inv.json")]) == 0
    out = capsys.readouterr().out
    assert "index.csv" in out and "3 .tif" in out
    mapping = tmp_path / "mapping.yaml"
    assert cli.main(["migrate", "records", "map", str(exp), "--out", str(mapping)]) == 0
    m = yaml.safe_load(mapping.read_text())
    assert m["layout"] == "one_row_per_party"
    assert m["columns"]["instrument_number"] == "InstNum" and m["columns"]["party_role"] == "PartyType"
    m["doc_type_map"] = {"WD": "Warranty Deed", "DT": "Deed of Trust", "REL": "Release of Lien"}
    m["columns"]["role_values"] = {"grantor": ["GR"], "grantee": ["GE"]}
    mapping.write_text(yaml.safe_dump(m))
    assert cli.main(["migrate", "records", "check", str(mapping)]) == 0
    out = capsys.readouterr().out
    assert "Documents in the export:         4" in out
    assert "Unreadable date '13/45/2002'" in out
    assert "Documents with no image found:   1" in out
    assert cli.main(["migrate", "records", "load", str(mapping), "--yes"]) == 0
    with tx() as conn:
        batch = conn.execute(select(import_batches).where(import_batches.c.kind == "records")
                             .order_by(import_batches.c.id.desc())).mappings().first()
        rec = conn.execute(select(instruments).where(instruments.c.instrument_number == "1999-000124")).mappings().first()
    assert batch["rows_loaded"] == 4 and rec["page_count"] == 3 and rec["doc_type"] == "Deed of Trust"
    from fastapi.testclient import TestClient
    from portal.app import create_app
    c = TestClient(create_app())
    assert "FIRST STATE BANK" in c.get("/records?name=first+state").text
    assert c.get("/records/1999-000124/pages/3.png").status_code == 200
    assert "MUÑOZ ROSA" in c.get("/records?name=mu%C3%B1oz").text
    assert cli.main(["migrate", "records", "verify", "--batch", str(batch["id"]), "--sample", "10"]) == 0
    out = capsys.readouterr().out
    assert "4 of 4 sampled documents match" in out
    # Loading again skips what is already there.
    assert cli.main(["migrate", "records", "load", str(mapping), "--yes"]) == 0
    assert "0 documents loaded" in capsys.readouterr().out


def test_bills_sync(tmp_path, capsys):
    f = tmp_path / "taxroll.csv"
    f.write_text("Acct,Owner,Situs,Total Due\nT-1,ANN LEE,1 MAIN,\"1,250.75\"\nT-2,BO RAY,2 MAIN,0\n")
    out = tmp_path / "bills.yaml"
    assert cli.main(["migrate", "bills", "map", str(f), "--kind", "property_tax", "--office", "tax-office",
                     "--out", str(out)]) == 0
    m = yaml.safe_load(out.read_text())
    assert m["columns"]["account"] == "Acct" and m["columns"]["amount_due"] == "Total Due"
    assert cli.main(["migrate", "bills", "check", str(out)]) == 0
    assert "Total due: $1,250.75" in capsys.readouterr().out
    assert cli.main(["migrate", "bills", "load", str(out)]) == 0
    with tx() as conn:
        t1 = conn.execute(select(receivables.c.amount_due_cents).where(receivables.c.account == "T-1")).scalar_one()
        demo = conn.execute(select(receivables.c.amount_due_cents).where(receivables.c.account == "R000456")).scalar_one()
    assert t1 == 125075
    assert demo == 0  # sync: accounts missing from the new roll are set to $0 due
    # Undo puts the bills back exactly as before the load.
    batch = int(re.search(r"Batch (\d+)\. Bills", capsys.readouterr().out).group(1))
    assert cli.main(["migrate", "bills", "undo", "--batch", str(batch)]) == 0
    with tx() as conn:
        assert conn.execute(select(receivables.c.id).where(receivables.c.account == "T-1")).first() is None
        assert conn.execute(select(receivables.c.amount_due_cents)
                            .where(receivables.c.account == "R000456")).scalar_one() > 0


def test_bill_sync_refuses_truncated_file(tmp_path):
    with tx() as conn:
        for i in range(30):
            conn.execute(receivables.insert().values(kind="utility", account=f"U-{i}", office_slug="tax-office",
                                                     name="SAMPLE", amount_due_cents=1000, allow_partial=True))
    f = tmp_path / "utility.csv"
    f.write_text("Account,Name,Balance\nU-1,SAMPLE,10.00\n")
    out = tmp_path / "u.yaml"
    assert cli.main(["migrate", "bills", "map", str(f), "--kind", "utility", "--office", "tax-office",
                     "--out", str(out)]) == 0
    with pytest.raises(SystemExit) as exc:
        cli.main(["migrate", "bills", "load", str(out)])
    assert "Nothing was changed" in str(exc.value)
    with tx() as conn:
        assert conn.execute(select(receivables.c.amount_due_cents).where(receivables.c.account == "U-5")).scalar_one() == 1000
        conn.execute(receivables.delete().where(receivables.c.kind == "utility"))


def test_site_crawl_and_import(tmp_path, capsys):
    site = tmp_path / "oldsite"
    (site / "departments").mkdir(parents=True)
    (site / "docs").mkdir()
    (site / "index.html").write_text("""<html><head><title>Old County</title><style>.hdr{background:#7a1f1f}
      a{color:#7a1f1f} .btn{background:#7a1f1f}</style></head><body><header>Old header</header>
      <nav><a href="/departments/clerk.html">Clerk</a></nav><main><h1>Welcome to Old County</h1>
      <p>Our courthouse is open weekdays. See the <a href="/departments/clerk.html">County Clerk</a>
      and the <a href="/docs/budget.pdf">2026 budget</a>.</p><img src="/seal.png"></main><footer>f</footer></body></html>""")
    (site / "departments" / "clerk.html").write_text("""<html><head><title>Clerk</title></head><body><div id="content">
      <h1>County Clerk</h1><p>The County Clerk records deeds and issues marriage licenses for the whole county.</p>
      <table><tr><td>Fee</td><td>$5</td></tr></table></div></body></html>""")
    (site / "docs" / "budget.pdf").write_bytes(b"%PDF-1.4 sample budget")
    handler = partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        assert cli.main(["migrate", "site", "crawl", url, "--delay", "0", "--ignore-robots"]) == 0
        assert cli.main(["migrate", "site", "import"]) == 0
    finally:
        server.shutdown()
    out = capsys.readouterr().out
    assert "Imported 2 pages" in out
    with tx() as conn:
        clerk = conn.execute(select(pages).where(pages.c.title == "County Clerk")).mappings().first()
        home = conn.execute(select(pages).where(pages.c.title == "Welcome to Old County")).mappings().first()
        redirect = conn.execute(select(redirects.c.new_path).where(redirects.c.old_path == "/departments/clerk.html")).scalar()
    assert clerk and not clerk["published"] and "table" in clerk["review_note"]
    assert "/pages/departments/clerk" in home["body"] and "/files/" in home["body"]
    assert "no description" in home["review_note"]
    assert redirect == "/pages/departments/clerk"
