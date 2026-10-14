#!/usr/bin/env python3
"""Open County Portal conformance suite.

Checks a running portal, at any address, against what the project promises:

  accessibility  WCAG 2.1 AA automated checks (axe-core) on every public page, at
                 desktop and phone widths, plus keyboard, reflow and form-error checks
  no-js          the core pages and forms work with JavaScript turned off
  api            the open API answers without a key, matches its published OpenAPI
                 document, allows cross-origin use, and pages correctly
  bulk           every bulk file downloads and matches its published checksum
  catalog        /data.json (DCAT-US 3.0) and /data-v1.1.json have what Data.gov needs
  security       HTTPS and basic protective headers

Usage (from the project folder):
  python3 conformance/run.py --url https://portal.example-county.gov
  python3 conformance/run.py --url http://localhost:8000 --only api,catalog

Automated checks find roughly a third to a half of accessibility problems.
They don't replace the manual review in docs/admin/accessibility-testing.md.

Results print as PASS / WARN / FAIL lines and are saved as an HTML and a JSON report in
conformance/reports/. The exit code is 1 if anything failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

HERE = Path(__file__).resolve().parent
AXE_JS = HERE / "node_modules" / "axe-core" / "axe.min.js"
FAIL_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
WARN_TAGS = ["wcag22aa", "best-practice"]
SKIP_PREFIXES = ("/staff/", "/api/", "/static/", "/checkout/", "/payments/", "/files/", "/verify/")
SKIP_SUFFIXES = (".pdf", ".png", ".jpg", ".csv", ".json", ".jsonl", ".xml", ".zip", ".ics")


@dataclass
class Result:
    group: str
    status: str  # PASS | WARN | FAIL | SKIP
    check: str
    detail: str = ""
    where: str = ""


@dataclass
class Report:
    url: str
    started: str
    results: list[Result] = field(default_factory=list)

    def add(self, group: str, status: str, check: str, detail: str = "", where: str = "") -> None:
        r = Result(group, status, check, detail, where)
        self.results.append(r)
        mark = {"PASS": "\033[32mPASS\033[0m", "WARN": "\033[33mWARN\033[0m", "FAIL": "\033[31mFAIL\033[0m",
                "SKIP": "SKIP"}[status]
        loc = f"  [{where}]" if where else ""
        print(f"  {mark}  {check}{loc}" + (f"\n        {detail}" if detail and status != "PASS" else ""))

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
        for r in self.results:
            out[r.status] += 1
        return out


# ---- helpers ---------------------------------------------------------------------

def same_origin(base: str, link: str) -> bool:
    a, b = urlparse(base), urlparse(link)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


def discover_pages(client: httpx.Client, base: str, limit: int) -> list[str]:
    """Breadth-first crawl of public pages starting at the home page."""
    seen: list[str] = []
    queue = ["/", "/services", "/offices", "/meetings", "/notices", "/records", "/pay", "/cart",
             "/public-information", "/records/redaction-request", "/data", "/accessibility", "/search?q=tax"]
    while queue and len(seen) < limit:
        path = queue.pop(0)
        if path in seen:
            continue
        try:
            r = client.get(urljoin(base, path))
        except httpx.HTTPError:
            continue
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            continue
        seen.append(path)
        for href in re.findall(r'href="([^"#]+)"', r.text):
            full = urljoin(urljoin(base, path), html.unescape(href))
            if not same_origin(base, full):
                continue
            p = urlparse(full)
            rel = p.path + (f"?{p.query}" if p.query else "")
            if rel.startswith(SKIP_PREFIXES) or p.path.endswith(SKIP_SUFFIXES) or rel in seen or rel in queue:
                continue
            if "/pages/" in rel and rel.count("/") > 4:
                continue
            queue.append(rel)
    return seen


# ---- accessibility ---------------------------------------------------------------

def check_accessibility(rep: Report, base: str, pages: list[str], with_forms: bool, insecure: bool = False) -> None:
    g = "accessibility"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        rep.add(g, "SKIP", "Browser checks", "Playwright isn't installed. See conformance/README.md.")
        return
    if not AXE_JS.exists():
        rep.add(g, "SKIP", "Browser checks", "axe-core isn't installed. Run: (cd conformance && npm ci)")
        return
    axe_source = AXE_JS.read_text(encoding="utf-8")

    def run_axe(page) -> dict:
        page.evaluate(axe_source)
        return page.evaluate("""async (tags) => await axe.run(document, {
            runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']})""", FAIL_TAGS + WARN_TAGS)

    def report_axe(result: dict, where: str) -> None:
        fails = [v for v in result["violations"] if set(v["tags"]) & set(FAIL_TAGS)]
        warns = [v for v in result["violations"] if v not in fails]
        if fails:
            for v in fails:
                nodes = "; ".join(n["target"][0] if isinstance(n["target"][0], str) else str(n["target"][0])
                                  for n in v["nodes"][:3])
                rep.add(g, "FAIL", f"WCAG: {v['help']} ({v['id']})", f"{len(v['nodes'])} element(s), e.g. {nodes}. "
                        f"{v['helpUrl']}", where)
        else:
            rep.add(g, "PASS", "No automated WCAG 2.1 A/AA violations", where=where)
        for v in warns:
            rep.add(g, "WARN", f"Advisory: {v['help']} ({v['id']})", f"{len(v['nodes'])} element(s). {v['helpUrl']}",
                    where)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        desktop = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=insecure)
        phone = browser.new_context(viewport={"width": 320, "height": 640}, device_scale_factor=2, is_mobile=True,
                                    has_touch=True, ignore_https_errors=insecure)
        for path in pages:
            url = urljoin(base, path)
            page = desktop.new_page()
            page.goto(url, wait_until="load")
            report_axe(run_axe(page), path)
            info = page.evaluate("""() => ({
                lang: document.documentElement.lang,
                title: document.title,
                h1: document.querySelectorAll('h1').length,
                main: document.querySelectorAll('main').length})""")
            if not info["lang"]:
                rep.add(g, "FAIL", "Page language is set", "The <html> element has no lang attribute.", path)
            if info["h1"] != 1:
                rep.add(g, "WARN", "Exactly one main heading", f"Found {info['h1']} <h1> elements.", path)
            if info["main"] != 1:
                rep.add(g, "FAIL", "One <main> landmark", f"Found {info['main']}.", path)
            # Keyboard: the first Tab should land on a working skip link, with a visible focus indicator.
            page.keyboard.press("Tab")
            focus = page.evaluate("""() => {
                const el = document.activeElement; if (!el || el === document.body) return null;
                const cs = getComputedStyle(el);
                const href = el.getAttribute('href') || '';
                return {href, target: href.startsWith('#') && !!document.getElementById(href.slice(1)),
                        visible: (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== 'none',
                        text: (el.innerText || '').trim().slice(0, 40)};
            }""")
            if not focus or not focus["target"]:
                rep.add(g, "FAIL", "First Tab reaches a skip link", f"Focused: {focus}", path)
            elif not focus["visible"]:
                rep.add(g, "FAIL", "Keyboard focus is visible", f"No outline or focus ring on '{focus['text']}'.", path)
            page.close()
            # Reflow (WCAG 1.4.10): no sideways scrolling at 320 CSS pixels.
            mp = phone.new_page()
            mp.goto(url, wait_until="load")
            width = mp.evaluate("() => document.documentElement.scrollWidth")
            if width > 322:
                rep.add(g, "FAIL", "Fits a 320-pixel phone screen without sideways scrolling",
                        f"Page is {width}px wide.", path)
            mp.close()
        if with_forms:
            check_form_errors(rep, desktop, base, pages, run_axe, report_axe)
        browser.close()


def check_form_errors(rep: Report, ctx, base: str, pages: list[str], run_axe, report_axe) -> None:
    """Submit each public form empty: the error page must summarize errors, link to fields and pass axe."""
    g = "accessibility"
    tried = 0
    for path in pages:
        if not path.startswith(("/apply/", "/records/redaction-request", "/public-information")):
            continue
        page = ctx.new_page()
        page.goto(urljoin(base, path), wait_until="load")
        form = page.locator("main form[method=post]").first
        if form.count() == 0:
            page.close()
            continue
        tried += 1
        form.locator("button[type=submit], input[type=submit]").last.click()
        page.wait_for_load_state("load")
        page.wait_for_timeout(300)  # browsers apply autofocus just after load
        where = f"{path} (submitted empty)"
        summary = page.evaluate("""() => {
            const s = document.querySelector('.error-summary, [role=alert]');
            if (!s) return null;
            const links = [...s.querySelectorAll('a[href^="#"]')];
            return {links: links.length, broken: links.filter(a => !document.getElementById(a.getAttribute('href').slice(1))).length,
                    focused: document.activeElement === s || s.contains(document.activeElement),
                    invalid: document.querySelectorAll('[aria-invalid=true]').length,
                    described: [...document.querySelectorAll('[aria-invalid=true]')].filter(e => e.getAttribute('aria-describedby')).length};
        }""")
        if not summary:
            rep.add(g, "FAIL", "Form errors are summarized at the top", "No error summary found.", where)
        else:
            ok = summary["links"] > 0 and summary["broken"] == 0 and summary["invalid"] > 0 \
                and summary["described"] == summary["invalid"]
            rep.add(g, "PASS" if ok else "FAIL", "Form errors link to their fields and are announced",
                    "" if ok else json.dumps(summary), where)
            if not summary["focused"]:
                rep.add(g, "WARN", "Focus moves to the error summary", "Keyboard and screen reader users may miss it.",
                        where)
        report_axe(run_axe(page), where)
        page.close()
    if tried == 0:
        rep.add(g, "SKIP", "Form error checks", "No public forms with required fields were found.")


# ---- no-JavaScript ---------------------------------------------------------------

def check_no_js(rep: Report, client: httpx.Client, base: str) -> None:
    g = "no-js"
    r = client.get(urljoin(base, "/"))
    rep.add(g, "PASS" if r.status_code == 200 and "<main" in r.text else "FAIL", "Home page renders on the server")
    r = client.get(urljoin(base, "/records"), params={"q": "a"})
    ok = r.status_code == 200 and "<form" in r.text
    rep.add(g, "PASS" if ok else "FAIL", "Records search works as a plain HTML form")
    r = client.get(urljoin(base, "/pay"))
    rep.add(g, "PASS" if r.status_code == 200 else "FAIL", "Payments start page renders without scripts")
    r = client.get(urljoin(base, "/this-page-does-not-exist-conformance"))
    ok = r.status_code == 404 and "text/html" in r.headers.get("content-type", "")
    rep.add(g, "PASS" if ok else "FAIL", "Missing pages return a helpful 404 page, not an error dump")


# ---- API -------------------------------------------------------------------------

def check_api(rep: Report, client: httpx.Client, base: str) -> None:
    g = "api"
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        Draft202012Validator = None  # noqa: N806
    r = client.get(urljoin(base, "/api/v1/openapi.json"))
    if r.status_code != 200:
        rep.add(g, "FAIL", "OpenAPI document is published at /api/v1/openapi.json", f"HTTP {r.status_code}")
        return
    spec = r.json()
    rep.add(g, "PASS" if str(spec.get("openapi", "")).startswith("3.") else "FAIL",
            "OpenAPI document is OpenAPI 3", f"openapi = {spec.get('openapi')}")
    registry = None
    if Draft202012Validator:
        registry = Registry().with_resource("urn:oas", Resource.from_contents(spec, default_specification=DRAFT202012))
    else:
        rep.add(g, "WARN", "Response schemas checked", "Install jsonschema to validate responses against the schema.")

    first_instrument = None
    for path, ops in sorted(spec.get("paths", {}).items()):
        if "get" not in ops or not path.startswith("/api/v1"):
            continue
        params = {}
        concrete = path
        if "{number}" in path:
            if not first_instrument:
                rep.add(g, "SKIP", f"GET {path}", "No public instruments to test with.")
                continue
            concrete = path.replace("{number}", first_instrument)
        elif "{" in path:
            continue  # bulk/{name} is covered by the bulk checks
        for p in ops["get"].get("parameters", []):
            if p.get("required") and p["in"] == "query":
                if p["name"] == "since":
                    params["since"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3650)).isoformat()
        resp = client.get(urljoin(base, concrete), params=params, headers={"Origin": "https://example.org"})
        where = f"GET {concrete}"
        if resp.status_code != 200:
            rep.add(g, "FAIL", "Answers without an API key", f"HTTP {resp.status_code}: {resp.text[:200]}", where)
            continue
        problems = []
        if resp.headers.get("access-control-allow-origin") != "*":
            problems.append("missing Access-Control-Allow-Origin: *")
        try:
            body = resp.json()
        except ValueError:
            rep.add(g, "FAIL", "Returns JSON", resp.headers.get("content-type", ""), where)
            continue
        if path == "/api/v1/instruments" and body.get("data"):
            first_instrument = body["data"][0]["instrument_number"]
        schema = ops["get"].get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")
        if registry is not None and schema and schema != {}:
            wrapped = json.loads(json.dumps(schema).replace('"#/', '"urn:oas#/'))
            errs = list(Draft202012Validator(wrapped, registry=registry).iter_errors(body))
            if errs:
                problems.append("doesn't match its schema: " + "; ".join(e.message[:120] for e in errs[:3]))
        rep.add(g, "FAIL" if problems else "PASS", "Open, cross-origin, matches the published schema",
                "; ".join(problems), where)
        # Paging: follow one 'next' link if there is one.
        if isinstance(body, dict) and body.get("next"):
            if not same_origin(base, body["next"]):
                rep.add(g, "WARN", "Next-page link points to the address being tested",
                        f"It points to {body['next']}; check PORTAL_SITE_URL if this isn't the public address.", where)
            else:
                nxt = client.get(body["next"])
                rep.add(g, "PASS" if nxt.status_code == 200 else "FAIL", "Next-page link works", body["next"], where)


def check_bulk(rep: Report, client: httpx.Client, base: str) -> None:
    g = "bulk"
    r = client.get(urljoin(base, "/api/v1/bulk"))
    if r.status_code != 200:
        rep.add(g, "FAIL", "Bulk manifest at /api/v1/bulk", f"HTTP {r.status_code}")
        return
    man = r.json()
    files = man.get("files", [])
    if not files:
        rep.add(g, "WARN", "Bulk files exist", man.get("message", "No files listed. They are written nightly."))
        return
    age = None
    try:
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(man["generated_at"])).total_seconds() / 3600
    except (KeyError, ValueError):
        pass
    if age is None or age > 36:
        rep.add(g, "WARN", "Bulk files are fresh (made in the last 36 hours)", f"generated_at = {man.get('generated_at')}")
    else:
        rep.add(g, "PASS", "Bulk files are fresh", f"{age:.0f} hours old")
    for f in files:
        if not same_origin(base, f["url"]):
            rep.add(g, "WARN", "Bulk file link points to the address being tested",
                    f"It points to {f['url']}; check PORTAL_SITE_URL if this isn't the public address.", f["name"])
            continue
        resp = client.get(f["url"])
        digest = hashlib.sha256(resp.content).hexdigest()
        ok = resp.status_code == 200 and digest == f["sha256"] and len(resp.content) == f["bytes"]
        rep.add(g, "PASS" if ok else "FAIL", "Downloads and matches its checksum",
                "" if ok else f"HTTP {resp.status_code}, sha256 {digest[:12]}… expected {f['sha256'][:12]}…", f["name"])


# ---- Data.gov catalogs -----------------------------------------------------------

def _email_ok(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"mailto:[^@\s]+@[^@\s]+\.[^@\s]+", v) is not None


def check_catalog(rep: Report, client: httpx.Client, base: str, check_links: bool) -> None:
    g = "catalog"
    r = client.get(urljoin(base, "/data.json"))
    if r.status_code != 200:
        rep.add(g, "FAIL", "/data.json is published", f"HTTP {r.status_code}")
        return
    cat = r.json()
    where = "/data.json (DCAT-US 3.0)"
    conforms = (cat.get("conformsTo") or {}).get("identifier", "")
    rep.add(g, "PASS" if "dcat-us/3" in conforms else "WARN", "Declares DCAT-US 3.0 in conformsTo", conforms, where)
    datasets = cat.get("dataset")
    if not isinstance(datasets, list) or not datasets:
        rep.add(g, "FAIL", "Has a dataset list (mandatory)", "", where)
        return
    ids = [d.get("identifier") for d in datasets]
    rep.add(g, "PASS" if len(ids) == len(set(ids)) else "FAIL", "Dataset identifiers are unique", "", where)
    for d in datasets:
        name = d.get("title", "(no title)")
        missing = [k for k in ("title", "description", "identifier") if not d.get(k)]
        cps = d.get("contactPoint")
        cps = cps if isinstance(cps, list) else [cps] if cps else []
        if not cps or not all(c.get("fn") and _email_ok(c.get("hasEmail")) for c in cps):
            missing.append("contactPoint with fn and a real mailto: hasEmail "
                           "(set it in Staff console > Settings > Records and open data)")
        rep.add(g, "FAIL" if missing else "PASS", "Mandatory fields present",
                "Missing: " + "; ".join(missing) if missing else "", f"{where}: {name}")
        rec = [k for k in ("keyword", "modified", "publisher", "distribution", "license") if not d.get(k)]
        if rec:
            rep.add(g, "WARN", "Recommended fields present", "Missing: " + ", ".join(rec), f"{where}: {name}")
        for dist in d.get("distribution") or []:
            link = dist.get("downloadURL") or dist.get("accessURL")
            if not link or not dist.get("mediaType"):
                rep.add(g, "FAIL", "Each distribution has a URL and media type", json.dumps(dist)[:160], name)
            elif check_links and not same_origin(base, link):
                rep.add(g, "WARN", "Distribution link points to the address being tested",
                        f"It points to {link}; check PORTAL_SITE_URL if this isn't the public address.", name)
            elif check_links:
                resp = client.get(link)
                rep.add(g, "PASS" if resp.status_code == 200 else "FAIL", "Distribution link works",
                        f"HTTP {resp.status_code}", link)
    # Project Open Data 1.1 (still harvested by Data.gov)
    r = client.get(urljoin(base, "/data-v1.1.json"))
    where = "/data-v1.1.json (DCAT-US 1.1)"
    if r.status_code != 200:
        rep.add(g, "WARN", "DCAT-US 1.1 catalog is published", f"HTTP {r.status_code}", where)
        return
    cat = r.json()
    ok = cat.get("conformsTo") == "https://project-open-data.cio.gov/v1.1/schema"
    rep.add(g, "PASS" if ok else "FAIL", "conformsTo is the v1.1 schema", str(cat.get("conformsTo")), where)
    for d in cat.get("dataset", []):
        missing = [k for k in ("title", "description", "modified", "identifier", "accessLevel") if not d.get(k)]
        if not d.get("keyword"):
            missing.append("keyword")
        if not (d.get("publisher") or {}).get("name"):
            missing.append("publisher.name")
        cp = d.get("contactPoint") or {}
        if not cp.get("fn") or not _email_ok(cp.get("hasEmail")):
            missing.append("contactPoint fn and a real mailto: hasEmail")
        if d.get("accessLevel") not in ("public", "restricted public", "non-public"):
            missing.append("accessLevel must be public, restricted public or non-public")
        rep.add(g, "FAIL" if missing else "PASS", "Required v1.1 fields present (non-federal)",
                "Missing: " + "; ".join(missing) if missing else "", f"{where}: {d.get('title')}")
    rep.add(g, "SKIP", "Official validator: paste /data.json into https://harvest.data.gov/validate/ "
            "(not automated here)")


# ---- security --------------------------------------------------------------------

def check_security(rep: Report, client: httpx.Client, base: str) -> None:
    g = "security"
    r = client.get(urljoin(base, "/"))
    h = r.headers
    if base.startswith("https://"):
        try:
            plain = httpx.get("http://" + base[len("https://"):], follow_redirects=False, timeout=10)
            ok = plain.status_code in (301, 302, 307, 308) and plain.headers.get("location", "").startswith("https://")
            rep.add(g, "PASS" if ok else "FAIL", "Plain http:// redirects to https://")
        except httpx.HTTPError as exc:
            rep.add(g, "WARN", "Plain http:// redirects to https://", f"Couldn't connect on port 80: {exc}")
        rep.add(g, "PASS" if "strict-transport-security" in h else "FAIL", "HSTS header is sent")
    else:
        rep.add(g, "WARN", "Served over HTTPS", "Testing a plain http:// address; fine for a test server only.")
    for name in ("content-security-policy", "x-content-type-options", "referrer-policy"):
        rep.add(g, "PASS" if name in h else "FAIL", f"{name} header is sent")
    rep.add(g, "PASS" if "server" not in h or not re.search(r"\d", h["server"]) else "WARN",
            "Server header doesn't reveal software versions", h.get("server", ""))


# ---- report ----------------------------------------------------------------------

def write_reports(rep: Report, out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    jpath = out / f"conformance-{stamp}.json"
    jpath.write_text(json.dumps({"url": rep.url, "started": rep.started, "counts": rep.counts(),
                                 "results": [asdict(r) for r in rep.results]}, indent=1), encoding="utf-8")
    rows = "\n".join(
        f"<tr class='{r.status.lower()}'><td>{r.status}</td><td>{html.escape(r.group)}</td>"
        f"<td>{html.escape(r.check)}</td><td>{html.escape(r.where)}</td><td>{html.escape(r.detail)}</td></tr>"
        for r in sorted(rep.results, key=lambda r: ("FAIL", "WARN", "SKIP", "PASS").index(r.status)))
    c = rep.counts()
    hpath = out / f"conformance-{stamp}.html"
    hpath.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conformance report</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:1rem;color:#1b1b1b}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}}tr.fail td:first-child{{background:#fde2e1;font-weight:700}}
tr.warn td:first-child{{background:#fff3c4}}tr.pass td:first-child{{background:#e3f4e1}}td{{overflow-wrap:anywhere}}</style></head>
<body><main><h1>Conformance report</h1><p>Site: {html.escape(rep.url)}<br>Run: {html.escape(rep.started)}</p>
<p><strong>{c['FAIL']} failed</strong>, {c['WARN']} warnings, {c['PASS']} passed, {c['SKIP']} skipped.</p>
<p>Automated checks catch only part of accessibility problems. Complete the manual review in
docs/admin/accessibility-testing.md before go-live.</p>
<table><caption class="visually-hidden">All results, failures first</caption><thead><tr><th scope="col">Result</th>
<th scope="col">Area</th><th scope="col">Check</th><th scope="col">Where</th><th scope="col">Detail</th></tr></thead>
<tbody>{rows}</tbody></table></main></body></html>""", encoding="utf-8")
    return jpath, hpath


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a running Open County Portal against the project's promises.")
    ap.add_argument("--url", required=True, help="Address of the portal, e.g. https://portal.example-county.gov")
    ap.add_argument("--only", default="", help="Comma list of areas: accessibility,no-js,api,bulk,catalog,security")
    ap.add_argument("--max-pages", type=int, default=40, help="Most pages to check for accessibility (default 40)")
    ap.add_argument("--no-forms", action="store_true", help="Don't submit forms (they create no records, but skip if unsure)")
    ap.add_argument("--no-link-check", action="store_true", help="Don't download every catalog link")
    ap.add_argument("--out", default=str(HERE / "reports"), help="Folder for the HTML and JSON reports")
    ap.add_argument("--insecure", action="store_true", help="Accept an untrusted certificate (internal mode test servers)")
    a = ap.parse_args(argv)
    base = a.url.rstrip("/") + "/"
    areas = set(a.only.split(",")) if a.only else {"accessibility", "no-js", "api", "bulk", "catalog", "security"}
    rep = Report(url=base, started=dt.datetime.now().isoformat(timespec="seconds"))
    print(f"Open County Portal conformance check: {base}")
    with httpx.Client(follow_redirects=True, timeout=30, verify=not a.insecure,
                      headers={"User-Agent": "open-county-portal-conformance/1.0"}) as client:
        try:
            client.get(urljoin(base, "/healthz")).raise_for_status()
        except httpx.HTTPError as exc:
            print(f"Can't reach {base}: {exc}")
            return 2
        if "security" in areas:
            print("\nSecurity"); check_security(rep, client, base)
        if "no-js" in areas:
            print("\nWorks without JavaScript"); check_no_js(rep, client, base)
        if "api" in areas:
            print("\nOpen API"); check_api(rep, client, base)
        if "bulk" in areas:
            print("\nBulk files"); check_bulk(rep, client, base)
        if "catalog" in areas:
            print("\nData.gov catalogs"); check_catalog(rep, client, base, not a.no_link_check)
        if "accessibility" in areas:
            print("\nAccessibility")
            pages = discover_pages(client, base, a.max_pages)
            print(f"  Checking {len(pages)} pages at desktop and 320px phone width: {', '.join(pages)}")
            check_accessibility(rep, base, pages, not a.no_forms, a.insecure)
    jpath, hpath = write_reports(rep, Path(a.out))
    c = rep.counts()
    print(f"\n{c['FAIL']} failed, {c['WARN']} warnings, {c['PASS']} passed, {c['SKIP']} skipped.")
    print(f"Report: {hpath}")
    return 1 if c["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
