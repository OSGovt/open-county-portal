"""Public website: every page renders, search works, forms validate."""
from __future__ import annotations

import pytest

from .conftest import csrf

PAGES = ["/", "/services", "/services/property-records", "/services/vehicle-registration", "/offices",
         "/offices/county-clerk", "/records", "/records?name=resident", "/records/2026-004812", "/pay",
         "/pay/property_tax", "/pay/property_tax?q=R000123", "/meetings", "/notices", "/public-information",
         "/public-information/archive", "/apply/vital-record", "/apply/jury-response", "/records/redaction-request",
         "/accessibility", "/data", "/cart", "/search?q=deed", "/sitemap.xml", "/robots.txt", "/theme.css", "/healthz"]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:500]}"


def test_html_basics(client):
    html = client.get("/").text
    assert '<html lang="en">' in html
    assert 'href="#main"' in html and 'id="main"' in html
    assert "<title>" in html and "Test County" in html


def test_unknown_page_is_friendly_404(client):
    r = client.get("/no-such-page")
    assert r.status_code == 404
    assert "find that page" in r.text and "<h1>" in r.text


def test_records_search_finds_party(client):
    r = client.get("/records?name=homeowner")
    assert "2026-004355" in r.text and "2024-002217" in r.text


def test_records_search_requires_something(client):
    r = client.get("/records?name=&doc_type=")
    assert r.status_code == 200


def test_records_bad_date_shows_error(client):
    r = client.get("/records?name=x&date_from=notadate")
    assert "Enter the start date" in r.text


def test_page_image_and_pdf(client):
    r = client.get("/records/2026-004812/pages/1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    r = client.get("/records/2026-004812/download.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_global_search_exact_instrument_redirects(client):
    r = client.get("/search?q=2026-004812", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/records/2026-004812")


def test_pia_validation_and_submit(client):
    token = csrf(client, "/public-information")
    r = client.post("/public-information", data={"_csrf": token, "description": "", "delivery": "email", "email": ""})
    assert r.status_code == 400 and "Describe the records" in r.text and 'role="alert"' in r.text
    r = client.post("/public-information", data={"_csrf": token, "description": "Road maintenance logs for 2025",
                                                  "delivery": "email", "email": "res@example.com"})
    assert r.status_code == 200 and "PIR-" in r.text


def test_csrf_required(client):
    r = client.post("/public-information", data={"description": "x", "delivery": "email", "email": "a@b.co"})
    assert r.status_code == 400


def test_form_without_fee(client):
    token = csrf(client, "/apply/jury-response")
    r = client.post("/apply/jury-response", data={"_csrf": token, "juror_number": "123", "full_name": "Pat Lee",
                                                  "email": "pat@example.com", "response": "I need to postpone",
                                                  "details": "Can serve in December"})
    assert r.status_code == 200 and "AP-" in r.text


def test_form_errors_are_linked(client):
    token = csrf(client, "/apply/jury-response")
    r = client.post("/apply/jury-response", data={"_csrf": token})
    assert r.status_code == 400
    assert 'href="#f-juror_number"' in r.text and 'aria-invalid="true"' in r.text


def test_redaction_request(client):
    token = csrf(client, "/records/redaction-request")
    r = client.post("/records/redaction-request", data={"_csrf": token, "requester_name": "Officer Sample",
                                                         "category": "Peace officer", "email": "o@example.gov",
                                                         "search_names": "SAMPLE OFFICER"}, follow_redirects=True)
    assert r.status_code == 200 and "RR-" in r.text


def test_security_headers(client):
    r = client.get("/")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_source_code_offered(client):
    """AGPL section 13: every visitor can download the running source."""
    assert '/source"' in client.get("/").text
    r = client.get("/source/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/gzip"
    import io
    import tarfile
    names = tarfile.open(fileobj=io.BytesIO(r.content)).getnames()
    assert any(n.endswith("/LICENSE") for n in names) and any(n.endswith("portal/app.py") for n in names)
    assert not any("__pycache__" in n for n in names)


def test_redacted_page_text_never_shows_original(client):
    """A redaction box hides part of the image; the machine-read text of the
    original must not leak what it hides, on the page or through the API."""
    from sqlalchemy import select

    from portal.db import images, instruments, redaction_marks, tx
    with tx() as conn:
        inst = conn.execute(select(instruments).where(instruments.c.status == "public")
                            .order_by(instruments.c.id)).mappings().first()
        img = conn.execute(select(images).where(images.c.instrument_id == inst["id"], images.c.seq == 1)).mappings().first()
        old_text = img["ocr_text"]
        conn.execute(images.update().where(images.c.id == img["id"])
                     .values(ocr_text="Grantor SSN 123-45-6789 SECRETWORD", redacted=True, public_text=None))
        mark = conn.execute(redaction_marks.insert().values(image_id=img["id"], x=10, y=10, w=100, h=20, reason="test")
                            .returning(redaction_marks.c.id)).scalar_one()
    try:
        number = inst["instrument_number"]
        assert "SECRETWORD" not in client.get(f"/records/{number}").text
        api = client.get(f"/api/v1/instruments/{number}").json()
        assert all(i["text"] is None for i in api["images"] if i["seq"] == 1)
        with tx() as conn:
            conn.execute(images.update().where(images.c.id == img["id"]).values(public_text="Grantor SSN [redacted]"))
        assert "Grantor SSN [redacted]" in client.get(f"/records/{number}").text
    finally:
        with tx() as conn:
            conn.execute(redaction_marks.delete().where(redaction_marks.c.id == mark))
            conn.execute(images.update().where(images.c.id == img["id"])
                         .values(ocr_text=old_text, redacted=False, public_text=None))


def test_change_feed_reports_unpublished_as_delete(client):
    from sqlalchemy import select

    from portal.db import services, tx, utcnow
    with tx() as conn:
        slug = conn.execute(select(services.c.slug).where(services.c.published.is_(True))).first()[0]
        conn.execute(services.update().where(services.c.slug == slug).values(published=False, updated_at=utcnow()))
    try:
        data = client.get("/api/v1/changes", params={"since": "2000-01-01T00:00:00Z"}).json()["data"]
        entry = [c for c in data if c["type"] == "service" and c["id"] == slug][-1]
        assert entry["change"] == "delete"
    finally:
        with tx() as conn:
            conn.execute(services.update().where(services.c.slug == slug).values(published=True))


def test_served_from_a_subfolder(monkeypatch):
    """PORTAL_BASE_PATH=/utopia: links, forms, redirects and cookies stay inside the subfolder."""
    import re as _re

    from fastapi.testclient import TestClient

    from portal.app import create_app
    from portal.settings import reset_settings_cache
    monkeypatch.setenv("PORTAL_BASE_PATH", "/utopia")
    monkeypatch.setenv("PORTAL_SITE_URL", "http://testserver/utopia")
    reset_settings_cache()
    try:
        with TestClient(create_app()) as c:
            home = c.get("/utopia/")
            assert home.status_code == 200
            links = _re.findall(r'(?:href|src|action)="(/[^"/][^"]*)"', home.text)
            assert links and all(l.startswith("/utopia/") or l == "/utopia" for l in links), links[:10]
            assert 'data-base="/utopia"' in home.text
            # also reachable when the front door strips the prefix
            assert c.get("/records").status_code == 200
            r = c.get("/utopia/staff/", follow_redirects=False)
            assert r.headers["location"].startswith("/utopia/staff/login")
            login = c.get("/utopia/staff/login")
            assert 'action="/utopia/staff/login"' in login.text
            assert "path=/utopia" in login.headers.get("set-cookie", "").lower() or "portal_session" not in login.headers.get("set-cookie", "")
            assert "Disallow: /utopia/staff/" in c.get("/utopia/robots.txt").text
            api = c.get("/utopia/api/v1/instruments", params={"limit": 1}).json()
            assert api["next"].startswith("http://testserver/utopia/api/v1/")
            css = c.get("/utopia/static/portal.css")
            assert css.status_code == 200
    finally:
        monkeypatch.delenv("PORTAL_BASE_PATH")
        monkeypatch.setenv("PORTAL_SITE_URL", "http://testserver")
        reset_settings_cache()


def test_demo_mode_keeps_crawlers_out(monkeypatch):
    from fastapi.testclient import TestClient

    from portal.app import create_app
    monkeypatch.setenv("PORTAL_DEMO_MODE", "1")
    with TestClient(create_app()) as c:
        robots = c.get("/robots.txt").text
        assert "Disallow: /records" in robots and "Disallow: /api/" in robots and "Disallow: /\n" not in robots
        assert "x-robots-tag" not in c.get("/").headers  # the demo's pages can be found in search
        assert "noindex" in c.get("/records?name=smith").headers["x-robots-tag"]
    monkeypatch.delenv("PORTAL_DEMO_MODE")
    with TestClient(create_app()) as c:
        assert "Disallow: /staff/" in c.get("/robots.txt").text
        assert "x-robots-tag" not in c.get("/").headers
