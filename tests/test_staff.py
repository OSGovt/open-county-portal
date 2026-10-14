"""Staff console: every page renders for an administrator; key workflows work."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from portal import config_store
from portal.db import fees, meetings, pages, redaction_marks, redirects, tx

from .conftest import csrf, staff_login

STAFF_PAGES = ["/staff/", "/staff/counter", "/staff/counter/orders", "/staff/counter/close", "/staff/orders",
               "/staff/orders?show=all", "/staff/pia", "/staff/pia?status=all", "/staff/applications",
               "/staff/applications?status=all", "/staff/content", "/staff/content/pages", "/staff/content/pages/new",
               "/staff/content/services", "/staff/content/services/1/edit", "/staff/content/offices",
               "/staff/content/meetings", "/staff/content/meetings/new", "/staff/content/postings",
               "/staff/content/postings/new", "/staff/content/redirects", "/staff/content/fees", "/staff/finance",
               "/staff/finance/ledger.csv", "/staff/finance/posting.csv", "/staff/records", "/staff/records?q=resident",
               "/staff/records/redactions", "/staff/records/2026-004812", "/staff/records/2026-004812/pages/1/redact",
               "/staff/records/2026-004812/pages/1/original.png", "/staff/settings", "/staff/settings/site",
               "/staff/settings/theme", "/staff/settings/theme/preview", "/staff/settings/theme/preview.css",
               "/staff/settings/payments", "/staff/settings/users", "/staff/settings/api-keys", "/staff/settings/forms",
               "/staff/system", "/staff/system/golive", "/staff/system/migrations", "/staff/system/audit"]


@pytest.fixture()
def admin(client):
    staff_login(client)
    return client


@pytest.mark.parametrize("path", STAFF_PAGES)
def test_staff_page_renders(admin, path):
    r = admin.get(path)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:800]}"


def test_post_a_meeting_publishes_notice(admin):
    token = csrf(admin, "/staff/content/meetings/new")
    r = admin.post("/staff/content/meetings/save", data={"_csrf": token, "body": "Commissioners Court",
                                                         "title": "Special meeting", "starts_at": "2030-01-15T09:00",
                                                         "location": "Courthouse", "agenda": "1. Budget",
                                                         "status": "posted"}, follow_redirects=True)
    assert "Saved the meeting" in r.text
    with tx() as conn:
        m = conn.execute(select(meetings).where(meetings.c.title == "Special meeting")).mappings().first()
    assert m["posted_at"] is not None
    assert "Special meeting" in admin.get("/meetings").text


def test_page_slug_validation(admin):
    token = csrf(admin, "/staff/content/pages/new")
    r = admin.post("/staff/content/pages/save", data={"_csrf": token, "title": "Burn bans", "slug": "Burn Bans!",
                                                      "body": "x"})
    assert r.status_code == 400 and "lowercase letters" in r.text
    r = admin.post("/staff/content/pages/save", data={"_csrf": token, "title": "Burn bans", "slug": "burn-bans",
                                                      "body": "## Current status\n\nNo ban.", "published": "on"},
                   follow_redirects=True)
    assert "Saved the page" in r.text
    assert "Current status" in admin.get("/pages/burn-bans").text


def test_redirect_from_old_address(admin, client):
    with tx() as conn:  # the migration tests may have imported this address already
        conn.execute(redirects.delete().where(redirects.c.old_path == "/departments/clerk.html"))
    token = csrf(admin, "/staff/content/redirects/new")
    admin.post("/staff/content/redirects/save", data={"_csrf": token, "old_path": "/departments/clerk.html",
                                                      "new_path": "/offices/county-clerk"})
    r = client.get("/departments/clerk.html", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/offices/county-clerk"
    # A second redirect for the same old address is refused with a message, not an error page.
    token = csrf(admin, "/staff/content/redirects/new")
    r = admin.post("/staff/content/redirects/save", data={"_csrf": token, "old_path": "/departments/clerk.html",
                                                          "new_path": "/offices"})
    assert r.status_code == 400 and "already a redirect" in r.text


def test_fee_confirm_and_schedule(admin):
    with tx() as conn:
        fid = conn.execute(select(fees.c.id).where(fees.c.code == "cert")).scalar_one()
    token = csrf(admin, "/staff/content/fees")
    r = admin.post("/staff/content/fees", data={"_csrf": token, "action": "confirm", "fee_id": fid, "adopted_by": ""},
                   follow_redirects=True)
    assert "Enter the order" in r.text
    r = admin.post("/staff/content/fees", data={"_csrf": token, "action": "confirm", "fee_id": fid,
                                                "adopted_by": "Order 2026-1"}, follow_redirects=True)
    assert "Fee confirmed" in r.text
    r = admin.post("/staff/content/fees", data={"_csrf": token, "action": "schedule", "code": "cert", "amount": "6.00",
                                                "effective_from": "2031-01-01", "adopted_by": "Order 2030-9"},
                   follow_redirects=True)
    assert "starting January 01, 2031" in r.text
    assert "$5.00" in admin.get("/api/v1/fees").text or "5.00" in admin.get("/api/v1/fees").text


def test_theme_publish_fixes_contrast(admin, client):
    token = csrf(admin, "/staff/settings/theme")
    r = admin.post("/staff/settings/theme", data={"_csrf": token, "action": "publish", "c_primary": "#99CCFF",
                                                  "c_link": "#AACCFF", "show_name_with_logo": "on"},
                   follow_redirects=True)
    assert "adjusted to meet contrast" in r.text
    with tx() as conn:
        t = config_store.get(conn, "theme")
    from portal.theme import check
    assert all(c.passed for c in check(t))
    css = client.get("/theme.css").text
    assert t["colors"]["primary"] in css


def test_theme_history_restore(admin):
    page = admin.get("/staff/settings/theme").text
    ids = re.findall(r'name="history_id" value="(\d+)"', page)
    assert ids
    token = csrf(admin, "/staff/settings/theme")
    r = admin.post("/staff/settings/theme", data={"_csrf": token, "action": "restore", "history_id": ids[-1]},
                   follow_redirects=True)
    assert "restored" in r.text


def test_add_user_shows_temp_password_once(admin):
    token = csrf(admin, "/staff/settings/users")
    r = admin.post("/staff/settings/users", data={"_csrf": token, "action": "add", "name": "Casey Cashier",
                                                  "email": "casey@test.gov", "roles": "cashier",
                                                  "offices": "county-clerk"}, follow_redirects=True)
    assert "Give this temporary password" in r.text
    assert "Give this temporary password" not in admin.get("/staff/settings/users").text


def test_cashier_cannot_open_settings(client):
    from portal import auth
    from portal.db import users
    with tx() as conn:
        if not conn.execute(select(users.c.id).where(users.c.email == "cash2@test.gov")).first():
            auth.create_user(conn, "cash2@test.gov", "Cash Two", ["cashier"], ["county-clerk"])
    staff_login(client, "cash2@test.gov")
    assert client.get("/staff/settings").status_code == 403
    assert client.get("/staff/counter").status_code == 200


def test_redaction_mark_changes_public_image(admin, client):
    before = client.get("/records/2026-004790/pages/1.png").content
    token = csrf(admin, "/staff/records/2026-004790/pages/1/redact")
    r = admin.post("/staff/records/2026-004790/pages/1/marks", data={"_csrf": token, "units": "percent", "x": "8",
                                                                     "y": "20", "w": "40", "h": "5",
                                                                     "reason": "Test redaction"}, follow_redirects=True)
    assert "Redaction added" in r.text
    after = client.get("/records/2026-004790/pages/1.png").content
    assert after != before
    original = admin.get("/staff/records/2026-004790/pages/1/original.png").content
    assert original != after
    with tx() as conn:
        assert conn.execute(select(redaction_marks)).first() is not None


def test_certified_pdf_issue_and_verify(admin, client):
    from .test_payments import _pay
    token = csrf(client, "/records/2026-004355")
    client.post("/cart/add", data={"_csrf": token, "kind": "certified_copy", "instrument": "2026-004355",
                                   "format": "electronic"})
    _pay(client)
    page = admin.get("/staff/orders").text
    line_id = re.search(r'/staff/orders/(\d+)/issue', page).group(1)
    token = csrf(admin, "/staff/orders")
    r = admin.post(f"/staff/orders/{line_id}/issue", data={"_csrf": token}, follow_redirects=True)
    code = re.search(r"verification code ([0-9A-F]{10})", r.text).group(1)
    v = client.get(f"/verify/{code}")
    assert v.status_code == 200 and "genuine certified copy" in v.text
    pdf = client.get(f"/verify/{code}/download")
    import hashlib
    assert hashlib.sha256(pdf.content).hexdigest() in v.text
    assert client.get("/verify/0000000000").status_code == 404


def test_help_page_renders(admin):
    r = admin.get("/staff/help")
    assert r.status_code in (200, 404)  # docs are added later in the build


def test_ssn_scan_lists_pages_for_review(capsys):
    from portal import cli
    from portal.db import images
    from portal.settings import get_settings
    with tx() as conn:
        image_id = conn.execute(select(images.c.id).order_by(images.c.id)).first()[0]
        old = conn.execute(select(images.c.ocr_text).where(images.c.id == image_id)).scalar()
        conn.execute(images.update().where(images.c.id == image_id).values(ocr_text="Grantor SSN: 123 45 6789"))
    try:
        assert cli.main(["ssn-scan"]) == 0
        report = (get_settings().migration_dir / "ssn-scan.csv").read_text()
        assert "***-**-6789" in report and "6789" in report and "123" not in report.split("\n", 1)[1].split(",")[3]
    finally:
        with tx() as conn:
            conn.execute(images.update().where(images.c.id == image_id).values(ocr_text=old))


def test_title2_deadline():
    from portal.compliance import title2_deadline
    assert str(title2_deadline({"jurisdiction_type": "county", "population": 120000})[0]) == "2027-04-26"
    assert str(title2_deadline({"jurisdiction_type": "county", "population": 9000})[0]) == "2028-04-26"
    assert str(title2_deadline({"jurisdiction_type": "special_district", "population": 900000})[0]) == "2028-04-26"
    assert title2_deadline({"jurisdiction_type": "county"})[0] is None


def test_every_state_pack_is_valid():
    """Every pack shipped in portal/statepacks validates and gives county and district profiles."""
    import yaml

    from portal import statepacks
    for path in sorted(statepacks.PACK_DIR.glob("*/pack.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert statepacks.validate(data) == [], path
        for kind in ("county", "special_district", "school_district", "municipality"):
            prof = statepacks.profile(data, kind)
            assert set(prof) >= {"offices", "services", "fees", "forms", "postings"}


def test_schema_upgrade_steps_run_in_order(monkeypatch):
    from portal import db
    from sqlalchemy import text
    monkeypatch.setattr(db, "SCHEMA_VERSION", db.SCHEMA_VERSION + 1)
    monkeypatch.setitem(db.MIGRATIONS, db.SCHEMA_VERSION,
                        ["CREATE TABLE IF NOT EXISTS upgrade_probe (id int)", "INSERT INTO upgrade_probe VALUES (1)"])
    with tx() as conn:
        before = db.schema_version(conn)
    try:
        db.create_schema()
        db.create_schema()  # running again does nothing more
        with tx() as conn:
            assert db.schema_version(conn) == before + 1
            assert conn.execute(text("SELECT count(*) FROM upgrade_probe")).scalar_one() == 1
    finally:
        with tx() as conn:
            conn.execute(text("DROP TABLE IF EXISTS upgrade_probe"))
            conn.execute(db.schema_info.delete().where(db.schema_info.c.version > before))


def test_every_guide_renders_in_help(admin):
    from pathlib import Path
    docs = Path(__file__).resolve().parent.parent / "docs"
    for md in sorted(docs.rglob("*.md")):
        rel = md.relative_to(docs).with_suffix("").as_posix()
        r = admin.get(f"/staff/help/{rel}")
        assert r.status_code == 200, rel
        assert "<h1" in r.text, rel
    # links between guides point inside Help
    assert 'href="/staff/help/admin/install"' in admin.get("/staff/help/admin/README").text


def test_stay_signed_in_and_idle_signout(client, monkeypatch):
    from portal import auth
    staff_login(client)
    assert client.post("/staff/ping").json() == {"ok": True}
    monkeypatch.setattr(auth, "STAFF_IDLE_SECONDS", -1)
    assert client.post("/staff/ping").json() == {"ok": False}
    r = client.get("/staff/", follow_redirects=False)
    assert r.status_code == 303 and "/staff/login" in r.headers["location"]
