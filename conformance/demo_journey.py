#!/usr/bin/env python3
"""Walk through a demonstration portal the way a visitor does.

Where run.py checks pages one at a time, this follows whole tasks end to end in
a real browser, on a site running with PORTAL_DEMO_MODE=1 (such as the public
Utopia County demo):

  wake      the site answers /healthz (a sleeping demo may take a while)
  home      the home page loads with the demonstration banner
  records   a records search finds documents; one opens; its page image and
            free PDF download work
  api       the open API answers a name search
  payment   a property tax bill goes from lookup to cart, checkout, the test
            processor and a receipt
  staff     the shared demo staff account signs in with its six-digit code and
            reaches the staff console and the counter

Every step must also stay on the site's own address: a redirect elsewhere (for
example to a placeholder host) is a failure.

Usage:
  python3 conformance/demo_journey.py --url https://utopia.osgovt.com
  python3 conformance/demo_journey.py --url ... --summary report.md

Exit code 1 if any step failed. It makes one test payment (no money moves) and
signs in once; on a demo both are erased when it resets.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

UA = "OSGovt-LiveCheck/1.0 (+https://github.com/OSGovt/open-county-portal)"


@dataclass
class Result:
    steps: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.steps.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)

    @property
    def failed(self) -> list[tuple[str, bool, str]]:
        return [s for s in self.steps if not s[1]]

    def markdown(self, base: str) -> str:
        lines = [f"Walk-through of {base}", "", "| Step | Result | Detail |", "|---|---|---|"]
        for name, ok, detail in self.steps:
            lines.append(f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail.replace('|', '/')} |")
        return "\n".join(lines) + "\n"


def wake(res: Result, base: str, wait_s: int) -> bool:
    start = time.time()
    last = ""
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=False) as client:
        while time.time() - start < wait_s:
            try:
                r = client.get(f"{base}/healthz")
                if r.status_code == 200:
                    detail = f"answered in {time.time() - start:.0f} s"
                    worker = r.headers.get("x-demo-worker-version")
                    if worker:  # the Cloudflare demo says which versions are serving
                        box = r.headers.get("x-demo-container-version", "unknown")
                        detail += f"; worker {worker[:8]}, container started by {box[:8]}"
                        if box != worker:
                            detail += " (container still on an older version)"
                    res.add("wake", True, detail)
                    return True
                last = f"HTTP {r.status_code}"
            except httpx.HTTPError as exc:
                last = type(exc).__name__
            time.sleep(5)
    res.add("wake", False, f"no answer from /healthz within {wait_s} s (last: {last})")
    return False


def run(base: str, wait_s: int) -> Result:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    res = Result()
    if not wake(res, base, wait_s):
        return res
    host = urlparse(base).netloc

    def on_site(page) -> bool:
        return urlparse(page.url).netloc == host

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=UA)
        ctx.set_default_timeout(45_000)
        page = ctx.new_page()

        def step(name, fn):
            try:
                ok, detail = fn()
                if ok and not on_site(page):
                    ok, detail = False, f"ended up at {page.url}, off the site"
                res.add(name, ok, detail)
            except (PWError, AssertionError, httpx.HTTPError, ValueError) as exc:
                msg = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
                res.add(name, False, f"{msg} (at {page.url})")

        def home():
            page.goto(base + "/")
            title = page.title()
            banner = page.get_by_text("Demonstration site").count() > 0
            return ("Utopia County" in title or "County" in title) and banner, f"title {title!r}, banner {'shown' if banner else 'missing'}"

        def records():
            page.goto(base + "/records?name=smith")
            links = page.locator("main a[href^='/records/']").filter(has_not_text="redaction")
            n = links.count()
            if n == 0:
                return False, "a search for 'smith' found no documents"
            href = links.first.get_attribute("href")
            links.first.click()
            page.wait_for_load_state()
            img = page.locator("main img[src*='/pages/']").first
            img.wait_for(state="visible")
            width = page.evaluate("(el) => el.complete ? el.naturalWidth : 0", img.element_handle())
            if not width:
                return False, f"{href}: the page image didn't load"
            pdf = page.request.get(base + href + "/download.pdf")
            body = pdf.body()
            if pdf.status != 200 or not body.startswith(b"%PDF"):
                return False, f"{href}/download.pdf answered {pdf.status} {pdf.headers.get('content-type')}"
            return True, f"{n} results; {href} shows its page image; PDF {len(body) // 1024} KB"

        def api():
            r = page.request.get(base + "/api/v1/instruments?name=garcia&limit=5")
            if r.status != 200:
                return False, f"HTTP {r.status}"
            data = r.json().get("data", [])
            return bool(data), f"{len(data)} documents for 'garcia'"

        def payment():
            page.goto(base + "/pay/property_tax?q=smith")
            forms = page.locator("main form[action='/cart/add']")
            if forms.count() == 0:
                return False, "no bills found for 'smith'"
            forms.first.get_by_role("button", name="Add to cart").click()
            page.wait_for_url(re.compile(r"/cart"))
            page.get_by_role("link", name="Continue to checkout").or_(
                page.get_by_role("button", name="Continue to checkout")).first.click()
            page.wait_for_url(re.compile(r"/checkout"))
            page.get_by_label("Email for your receipt").fill("livecheck@example.com")
            page.get_by_label(re.compile("Credit or debit card")).check()
            page.get_by_role("button", name="Continue to secure payment").click()
            page.wait_for_url(re.compile(r"/payments/test/pay"))
            page.get_by_label("Test card number").fill("4242 4242 4242 4242")
            page.get_by_role("button", name=re.compile(r"^Pay ")).click()
            page.wait_for_url(re.compile(r"/receipt/"), timeout=60_000)
            text = page.locator("main").inner_text()
            ok = "Receipt" in text or "receipt" in text
            return ok, f"paid with the test card; receipt {urlparse(page.url).path}"

        def staff():
            page.goto(base + "/staff/login")
            notice = page.locator("main").inner_text()
            email = re.search(r"[\w.+-]+@[\w.-]+\.example", notice)
            password = re.search(r"password\s+(\S+?)\.?\s", notice + " ")
            if not email or not password:
                return False, "the sign-in page doesn't show the demonstration account"
            form = page.locator("main form[action='/staff/login']")
            form.get_by_label("Email", exact=True).fill(email.group(0))
            form.get_by_label("Password", exact=True).fill(password.group(1))
            form.get_by_role("button").click()
            page.wait_for_url(re.compile(r"/staff/mfa"))
            code = re.search(r"current code is (\d{6})", page.locator("main").inner_text())
            if not code:
                return False, "the code page doesn't show the demonstration code"
            form = page.locator("main form[action='/staff/mfa']")
            form.get_by_label(re.compile("code", re.I)).fill(code.group(1))
            form.get_by_role("button").click()
            page.wait_for_load_state()
            if not on_site(page):
                return True, "redirected off the site"  # step() turns this into a failure with the address
            if "/staff/login" in page.url or "/staff/mfa" in page.url:
                return False, f"still on {urlparse(page.url).path} after entering the code"
            page.goto(base + "/staff/counter")
            ok = "/staff/counter" in page.url
            return ok, f"signed in; staff console at {urlparse(page.url).path}"

        for name, fn in (("home", home), ("records", records), ("api", api), ("payment", payment), ("staff", staff)):
            step(name, fn)
        browser.close()
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Walk through a demonstration portal end to end.")
    ap.add_argument("--url", required=True, help="Address of the demo, e.g. https://utopia.osgovt.com")
    ap.add_argument("--wait", type=int, default=240, help="Seconds to wait for a sleeping demo to wake (default 240)")
    ap.add_argument("--summary", help="Also write the results as a Markdown table to this file")
    args = ap.parse_args(argv)
    base = args.url.rstrip("/")
    res = run(base, args.wait)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as fh:
            fh.write(res.markdown(base))
    print(f"\n{len(res.steps) - len(res.failed)} passed, {len(res.failed)} failed")
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
