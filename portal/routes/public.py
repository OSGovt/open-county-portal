"""Public pages: home, search, services, offices, content pages, help."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import and_, or_, select

from .. import __version__, config_store
from ..db import files, get_engine, instruments, meetings, offices, pages, parties, services, utcnow
from ..settings import get_settings
from ..web import render

router = APIRouter()


def _published_services(conn):
    return conn.execute(select(services).where(services.c.published.is_(True))
                        .order_by(services.c.sort, services.c.title)).mappings().all()


@router.get("/", include_in_schema=False)
def home(request: Request):
    with get_engine().connect() as conn:
        featured = [s for s in _published_services(conn) if s["featured"]]
        next_meeting = conn.execute(select(meetings).where(meetings.c.status == "posted",
                                                           meetings.c.starts_at >= utcnow())
                                    .order_by(meetings.c.starts_at).limit(1)).mappings().first()
        return render(request, "public/home.html", conn, page_title="Home", featured=featured,
                      next_meeting=next_meeting)


@router.get("/search", include_in_schema=False)
def search(request: Request, q: str = ""):
    q = q.strip()[:200]
    with get_engine().connect() as conn:
        svc, pg, recs = [], [], []
        if q:
            exact = conn.execute(select(instruments.c.instrument_number)
                                 .where(instruments.c.instrument_number == q,
                                        instruments.c.status == "public")).scalar()
            if exact:
                return RedirectResponse(f"/records/{exact}", status_code=303)
            like = f"%{q}%"
            svc = conn.execute(select(services).where(
                services.c.published.is_(True),
                or_(services.c.title.ilike(like), services.c.summary.ilike(like), services.c.keywords.ilike(like)))
                .order_by(services.c.sort).limit(10)).mappings().all()
            if not svc:
                words = [w for w in re.split(r"\W+", q.lower()) if len(w) > 2]
                if words:
                    svc = conn.execute(select(services).where(
                        services.c.published.is_(True),
                        or_(*[or_(services.c.title.ilike(f"%{w}%"), services.c.keywords.ilike(f"%{w}%")) for w in words]))
                        .order_by(services.c.sort).limit(10)).mappings().all()
            pg = conn.execute(select(pages.c.slug, pages.c.title).where(
                pages.c.published.is_(True), or_(pages.c.title.ilike(like), pages.c.body.ilike(like)))
                .limit(10)).mappings().all()
            recs = conn.execute(select(instruments.c.instrument_number, instruments.c.doc_type,
                                       instruments.c.recorded_date).distinct()
                                .join(parties, parties.c.instrument_id == instruments.c.id)
                                .where(instruments.c.status == "public", parties.c.name_norm.ilike(f"%{q.upper()}%"))
                                .order_by(instruments.c.recorded_date.desc()).limit(5)).mappings().all()
        return render(request, "public/search.html", conn, page_title=f"Search results for {q}" if q else "Search",
                      q=q, services_found=svc, pages_found=pg, records_found=recs)


@router.get("/services", include_in_schema=False)
def service_list(request: Request):
    with get_engine().connect() as conn:
        groups: dict[str, list] = {}
        for s in _published_services(conn):
            groups.setdefault(s["category"] or "Other services", []).append(s)
        return render(request, "public/services.html", conn, page_title="Services", nav="services", groups=groups)


@router.get("/services/{slug}", include_in_schema=False)
def service_detail(request: Request, slug: str):
    with get_engine().connect() as conn:
        s = conn.execute(select(services).where(services.c.slug == slug, services.c.published.is_(True))).mappings().first()
        if s is None:
            raise HTTPException(404)
        office = conn.execute(select(offices).where(offices.c.slug == s["office_slug"])).mappings().first()
        return render(request, "public/service.html", conn, page_title=s["title"], nav="services", s=s, office=office)


@router.get("/offices", include_in_schema=False)
def office_list(request: Request):
    with get_engine().connect() as conn:
        rows = conn.execute(select(offices).where(offices.c.active.is_(True)).order_by(offices.c.sort, offices.c.name)).mappings().all()
        return render(request, "public/offices.html", conn, page_title="Offices and hours", nav="offices", offices=rows)


@router.get("/offices/{slug}", include_in_schema=False)
def office_detail(request: Request, slug: str):
    with get_engine().connect() as conn:
        o = conn.execute(select(offices).where(offices.c.slug == slug, offices.c.active.is_(True))).mappings().first()
        if o is None:
            raise HTTPException(404)
        svc = conn.execute(select(services).where(services.c.office_slug == slug, services.c.published.is_(True))
                           .order_by(services.c.sort)).mappings().all()
        return render(request, "public/office.html", conn, page_title=o["name"], nav="offices", o=o, office_services=svc)


@router.get("/pages/{slug:path}", include_in_schema=False)
def page(request: Request, slug: str):
    with get_engine().connect() as conn:
        p = conn.execute(select(pages).where(pages.c.slug == slug, pages.c.published.is_(True))).mappings().first()
        if p is None:
            raise HTTPException(404)
        return render(request, "public/page.html", conn, page_title=p["title"], p=p)


@router.get("/accessibility", include_in_schema=False)
def accessibility(request: Request):
    with get_engine().connect() as conn:
        return render(request, "public/accessibility.html", conn, page_title="Accessibility")


@router.get("/data", include_in_schema=False)
def open_data(request: Request):
    with get_engine().connect() as conn:
        od = config_store.get(conn, "open_data")
        s = get_settings()
        return render(request, "public/data.html", conn, page_title="Open data and API", od=od,
                      api_rate=s.api_rate_per_minute, api_rate_keyed=s.api_rate_per_minute_keyed)


@router.get("/files/{file_id}", include_in_schema=False)
def serve_file(file_id: int):
    with get_engine().connect() as conn:
        f = conn.execute(select(files).where(files.c.id == file_id)).mappings().first()
    if f is None:
        raise HTTPException(404)
    path = (get_settings().files_dir / f["path"]).resolve()
    if not str(path).startswith(str(get_settings().files_dir.resolve())) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type=f["mime"] or "application/octet-stream", filename=f["name"],
                        content_disposition_type="inline")


SOURCE_ITEMS = ("portal", "docs", "deploy", "conformance/run.py", "conformance/README.md", "conformance/package.json",
                "conformance/requirements.txt", "tests", "Dockerfile", "docker-compose.yml", "requirements.txt",
                "requirements-dev.txt", "VERSION", "LICENSE", "README.md", "CHANGELOG.md", ".env.example")


def _source_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


@router.get("/source", include_in_schema=False)
def source_page(request: Request):
    """AGPL section 13: everyone who uses the site can get the source code it runs."""
    with get_engine().connect() as conn:
        return render(request, "public/source.html", conn, page_title="Source code", version=__version__)


@router.get("/source/download", include_in_schema=False)
def source_download():
    import io
    import tarfile
    root = _source_root()
    # Key the cached archive by the newest file, so locally changed code is what gets served.
    stamp = max((int(p.stat().st_mtime) for item in SOURCE_ITEMS if (root / item).exists()
                 for p in ([root / item] if (root / item).is_file() else (root / item).rglob("*"))), default=0)
    cache = get_settings().cache_dir / f"open-county-portal-{__version__}-{stamp}-source.tar.gz"
    if not cache.exists():
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for item in SOURCE_ITEMS:
                path = root / item
                if path.exists():
                    tar.add(path, arcname=f"open-county-portal-{__version__}/{item}",
                            filter=lambda t: None if "__pycache__" in t.name or t.name.endswith(".pyc") else t)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(buf.getvalue())
        tmp.rename(cache)
    return FileResponse(cache, media_type="application/gzip", filename=cache.name)


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap() -> Response:
    base = get_settings().site_url
    urls = ["/", "/services", "/offices", "/records", "/pay", "/meetings", "/notices", "/public-information",
            "/data", "/accessibility"]
    with get_engine().connect() as conn:
        urls += [f"/services/{s}" for s in conn.execute(select(services.c.slug).where(services.c.published.is_(True))).scalars()]
        urls += [f"/offices/{s}" for s in conn.execute(select(offices.c.slug).where(offices.c.active.is_(True))).scalars()]
        urls += [f"/pages/{s}" for s in conn.execute(select(pages.c.slug).where(pages.c.published.is_(True))).scalars()]
    body = "".join(f"<url><loc>{base}{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    media_type="application/xml")
