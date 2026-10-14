"""Old website migration: copy pages and documents, then add redirects.

  crawl   reads the old site politely (one page a second by default), saves
          a complete raw copy as an archive, and downloads linked documents
  import  turns each saved page into an unpublished draft page, links
          documents, and creates a redirect from every old address

The old site is only read, never changed. Imported pages start unpublished:
staff review each one before it goes live, which is also the moment to fix
outdated content and accessibility problems the import flags.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import re
import time
import urllib.parse
import urllib.robotparser
from collections import deque
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify
from sqlalchemy import select

from ..db import audit, files, pages, redirects, tx, utcnow
from ..settings import get_settings

DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".txt", ".csv", ".odt", ".ods"}
SKIP_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", ".ico", ".zip", ".mp3", ".mp4", ".mov", ".wmv", ".exe"}
MAX_DOC_BYTES = 50 * 1024 * 1024
UA = "OpenCountyPortal site migration (read-only)"


def _work() -> Path:
    d = get_settings().migration_dir / "site"
    (d / "raw").mkdir(parents=True, exist_ok=True)
    return d


def _same_site(a: str, b: str) -> bool:
    ha, hb = urllib.parse.urlparse(a).hostname or "", urllib.parse.urlparse(b).hostname or ""
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def _clean(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path or "/", "", p.query, ""))


def crawl(start: str, max_pages: int = 3000, delay: float = 1.0, ignore_robots: bool = False, log=print) -> Path:
    work = _work()
    start = _clean(start)
    robots = urllib.robotparser.RobotFileParser()
    if not ignore_robots:
        try:
            robots.set_url(urllib.parse.urljoin(start, "/robots.txt"))
            robots.read()
        except Exception:
            ignore_robots = True
    index: dict[str, dict] = {}
    queue, seen = deque([start]), {start}
    docs: dict[str, dict] = {}
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as client:
        while queue and len(index) < max_pages:
            url = queue.popleft()
            if not ignore_robots and not robots.can_fetch(UA, url):
                continue
            try:
                r = client.get(url)
            except httpx.HTTPError as exc:
                index[url] = {"url": url, "error": exc.__class__.__name__}
                continue
            final = _clean(str(r.url))
            ctype = r.headers.get("content-type", "").split(";")[0].strip()
            if "html" not in ctype:
                continue
            key = hashlib.sha256(url.encode()).hexdigest()[:20]
            (work / "raw" / f"{key}.html").write_bytes(r.content)
            soup = BeautifulSoup(r.text, "html.parser")
            title = (soup.title.string or "").strip() if soup.title and soup.title.string else url
            entry = {"url": url, "final_url": final, "status": r.status_code, "file": f"{key}.html", "title": title,
                     "fetched_at": utcnow().isoformat()}
            index[url] = entry
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                target = _clean(urllib.parse.urljoin(final, href))
                if not target.startswith(("http://", "https://")) or not _same_site(target, start):
                    continue
                ext = Path(urllib.parse.urlparse(target).path).suffix.lower()
                if ext in DOC_EXTS:
                    docs.setdefault(target, {"url": target, "linked_from": url, "text": a.get_text(" ", strip=True)})
                elif ext not in SKIP_EXTS and target not in seen and target.count("?") <= 1 and len(target) < 500:
                    seen.add(target)
                    queue.append(target)
            if len(index) % 25 == 0:
                log(f"  {len(index)} pages read, {len(queue)} waiting, {len(docs)} documents found...")
            time.sleep(delay)
        log(f"Downloading {len(docs)} documents...")
        (work / "docs").mkdir(exist_ok=True)
        for d in docs.values():
            try:
                with client.stream("GET", d["url"]) as r:
                    size = int(r.headers.get("content-length") or 0)
                    if r.status_code != 200 or size > MAX_DOC_BYTES:
                        d["error"] = f"status {r.status_code}" if r.status_code != 200 else "too large"
                        continue
                    data = b""
                    for chunk in r.iter_bytes():
                        data += chunk
                        if len(data) > MAX_DOC_BYTES:
                            raise ValueError("too large")
                digest = hashlib.sha256(data).hexdigest()
                name = Path(urllib.parse.unquote(urllib.parse.urlparse(d["url"]).path)).name or "document"
                (work / "docs" / digest).write_bytes(data)
                d.update({"sha256": digest, "name": name, "bytes": len(data)})
            except Exception as exc:
                d["error"] = str(exc)[:100]
            time.sleep(delay / 2)
    (work / "index.json").write_text(json.dumps({"start": start, "crawled_at": utcnow().isoformat(),
                                                 "pages": index, "documents": docs}, indent=1), encoding="utf-8")
    log(f"Crawl finished: {len(index)} pages and {sum(1 for d in docs.values() if 'sha256' in d)} documents saved "
        f"to {work}. The old site was not changed.")
    return work


def _slug(url: str, used: set) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path).lower()
    path = re.sub(r"\.(html?|aspx?|php|cfm|jsp)$", "", path)
    path = re.sub(r"/(index|default|home)$", "", path)
    slug = re.sub(r"[^a-z0-9/]+", "-", path).strip("-/")
    slug = re.sub(r"/+", "/", slug)
    slug = re.sub(r"-+", "-", slug) or "home"
    base, n = slug[:180], 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _main_content(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript", "iframe", "form", "nav", "header", "footer", "aside"]):
        tag.decompose()
    for sel in ["main", "[role=main]", "#content", "#main-content", "#maincontent", ".content", "article", "#main"]:
        found = soup.select_one(sel)
        if found and len(found.get_text(strip=True)) > 80:
            return found
    return soup.body or soup


def import_site(log=print) -> dict:
    work = _work()
    data = json.loads((work / "index.json").read_text(encoding="utf-8"))
    settings = get_settings()
    counts = {"pages": 0, "documents": 0, "redirects": 0, "flags": 0}
    doc_map: dict[str, int] = {}
    with tx() as conn:
        used = set(conn.execute(select(pages.c.slug)).scalars())
        for d in data["documents"].values():
            if "sha256" not in d:
                continue
            existing = conn.execute(select(files.c.id).where(files.c.sha256 == d["sha256"])).scalar()
            if existing:
                doc_map[d["url"]] = existing
                continue
            rel = Path("migrated") / f"{d['sha256'][:12]}-{re.sub(r'[^A-Za-z0-9._-]', '_', d['name'])[-100:]}"
            dest = settings.files_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((work / "docs" / d["sha256"]).read_bytes())
            mime = mimetypes.guess_type(d["name"])[0] or "application/octet-stream"
            doc_map[d["url"]] = conn.execute(files.insert().values(
                name=d["name"], path=str(rel), mime=mime, sha256=d["sha256"], bytes=d["bytes"], source_url=d["url"],
                needs_accessibility_review=True).returning(files.c.id)).scalar_one()
            counts["documents"] += 1
        page_slugs: dict[str, str] = {}
        for url, p in data["pages"].items():
            if "file" in p and p.get("status") == 200:
                existing = conn.execute(select(pages.c.slug).where(pages.c.source_url == url)).scalar()
                page_slugs[url] = existing or _slug(url, used)
        for url, p in data["pages"].items():
            if url not in page_slugs:
                continue
            soup = BeautifulSoup((work / "raw" / p["file"]).read_bytes(), "html.parser")
            main = _main_content(soup)
            flags = []
            for img in main.find_all("img"):
                if not (img.get("alt") or "").strip():
                    flags.append("An image had no description (alt text); it was removed. Add it back with a description if it matters.")
                img.decompose()
            for a in main.find_all("a", href=True):
                target = _clean(urllib.parse.urljoin(p["final_url"], a["href"]))
                if target in doc_map:
                    a["href"] = f"/files/{doc_map[target]}"
                elif target in page_slugs:
                    a["href"] = f"/pages/{page_slugs[target]}"
            if main.find("table"):
                flags.append("This page has a table; check that it has a header row and reads sensibly.")
            if any(f"/files/{fid}" in str(main) for fid in doc_map.values()):
                flags.append("This page links to documents moved from the old site; check them for accessibility.")
            h1 = main.find("h1") or soup.find("h1")
            title = (h1.get_text(" ", strip=True) if h1 else p.get("title") or page_slugs[url])[:290]
            if h1:
                h1.decompose()
            body = markdownify(str(main), heading_style="ATX", strip=["span", "font"])
            body = re.sub(r"\n{3,}", "\n\n", body).strip()
            note = f"Imported from {url} on {dt.date.today()}." + ("\n- " + "\n- ".join(flags) if flags else "")
            counts["flags"] += len(flags)
            slug = page_slugs[url]
            if conn.execute(select(pages.c.id).where(pages.c.slug == slug)).first():
                conn.execute(pages.update().where(pages.c.slug == slug, pages.c.published.is_(False))
                             .values(title=title, body=body, review_note=note, updated_at=utcnow()))
            else:
                conn.execute(pages.insert().values(slug=slug, title=title, body=body, published=False, source_url=url,
                                                   review_note=note))
                counts["pages"] += 1
        for url, slug in page_slugs.items():
            old = urllib.parse.urlparse(url).path or "/"
            if old in ("", "/"):
                continue
            if conn.execute(select(redirects.c.old_path).where(redirects.c.old_path == old)).first() is None:
                conn.execute(redirects.insert().values(old_path=old, new_path=f"/pages/{slug}"))
                counts["redirects"] += 1
        for url, fid in doc_map.items():
            old = urllib.parse.urlparse(url).path
            if old and conn.execute(select(redirects.c.old_path).where(redirects.c.old_path == old)).first() is None:
                conn.execute(redirects.insert().values(old_path=old, new_path=f"/files/{fid}"))
                counts["redirects"] += 1
        audit(conn, "migration", "site.import", detail=counts)
    log(f"Imported {counts['pages']} pages (unpublished, waiting for review), {counts['documents']} documents, "
        f"{counts['redirects']} redirects. {counts['flags']} items were flagged for review.")
    return counts
