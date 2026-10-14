"""Application factory."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, config_store
from .db import get_engine, redirects
from .settings import get_settings
from .theme import css_variables, merged
from .web import render

STATIC_DIR = Path(__file__).parent / "static"


class RateLimiter:
    """Simple per-client sliding window. Protects the free API from overload
    without CAPTCHAs; heavy users are pointed to the bulk files."""

    def __init__(self) -> None:
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_dirs()
    app = FastAPI(title="Open County Portal API", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url="/api/v1/openapi.json",
                  description="Free, open API for public records and information published by this jurisdiction. "
                              "No key is required. Heavy users should download the daily bulk files at /api/v1/bulk.")
    limiter = RateLimiter()
    key_cache: dict = {"at": 0.0, "hashes": set()}

    def _key_ok(key: str) -> bool:
        """Check an API key against active keys, refreshing the list every minute."""
        import hashlib
        from .db import api_keys
        now = time.monotonic()
        if now - key_cache["at"] > 60:
            with get_engine().connect() as conn:
                key_cache["hashes"] = set(conn.execute(select(api_keys.c.key_hash).where(api_keys.c.active.is_(True))).scalars())
            key_cache["at"] = now
        return hashlib.sha256(key.encode()).hexdigest() in key_cache["hashes"]

    @app.middleware("http")
    async def security_and_limits(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            key_header = request.headers.get("x-api-key")
            valid_key = bool(key_header) and _key_ok(key_header)
            limit = settings.api_rate_per_minute_keyed if valid_key else settings.api_rate_per_minute
            ident = (key_header if valid_key else "") + "|" + (request.client.host if request.client else "?")
            if not limiter.allow(ident, limit):
                return JSONResponse({"error": "rate_limited",
                                     "message": "Too many requests this minute. Wait a minute, request a free API key, "
                                                "or use the daily bulk files at /api/v1/bulk."},
                                    status_code=429, headers={"Retry-After": "60"})
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
        if not path.startswith("/api/") and path not in ("/data.json", "/data-v1.1.json"):
            # Fonts and stylesheets may come from an https font service chosen in the theme.
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https:; font-src 'self' https:; "
                "script-src 'self'; form-action 'self' https:; frame-ancestors 'none'; base-uri 'self'")
            response.headers.setdefault("X-Frame-Options", "DENY")
        else:
            response.headers.setdefault("Access-Control-Allow-Origin", "*")
        if settings.secure_cookies:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="portal_session",
                       max_age=settings.session_max_age, same_site="lax", https_only=settings.secure_cookies,
                       path=settings.base_path or "/")
    if settings.base_path:  # outermost: everything inside sees plain paths
        from .basepath import BasePathMiddleware
        app.add_middleware(BasePathMiddleware, base=settings.base_path)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    import os
    if os.environ.get("PORTAL_NIGHTLY_IN_APP", "").lower() in ("1", "true", "yes"):
        from . import scheduler
        scheduler.start()

    @app.get("/theme.css", include_in_schema=False)
    def theme_css() -> Response:
        with get_engine().connect() as conn:
            theme = config_store.get(conn, "theme") or {}
        return Response(css_variables(merged(theme)), media_type="text/css",
                        headers={"Cache-Control": "public, max-age=300"})

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__}

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        b = settings.base_path
        return PlainTextResponse(f"User-agent: *\nDisallow: {b}/staff/\nDisallow: {b}/cart\nDisallow: {b}/checkout\n"
                                 f"Sitemap: {settings.site_url}/sitemap.xml\n")

    from .routes import api, apply, meetings, pay, public, records, staff  # noqa: E402
    app.include_router(api.router)
    app.include_router(api.catalog_router)
    app.include_router(records.router)
    app.include_router(pay.router)
    app.include_router(apply.router)
    app.include_router(meetings.router)
    app.include_router(staff.router)
    app.include_router(public.router)  # last: contains the catch-all for redirects

    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (301, 302, 303, 307) and exc.headers and "Location" in exc.headers:
            return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
        if request.url.path.startswith("/api/") or request.url.path.endswith(".json"):
            return JSONResponse({"error": exc.status_code, "message": exc.detail}, status_code=exc.status_code)
        if exc.status_code == 404:
            with get_engine().connect() as conn:
                target = conn.execute(select(redirects.c.new_path).where(
                    redirects.c.old_path == request.url.path)).scalar()
                if target:
                    return RedirectResponse(target, status_code=301)
                return render(request, "public/error.html", conn, status_code=404, page_title="Page not found",
                              heading="We couldn't find that page",
                              message="It may have moved when this site was updated. Try searching, or start from the home page.")
        with get_engine().connect() as conn:
            return render(request, "public/error.html", conn, status_code=exc.status_code,
                          page_title="Something went wrong", heading="Something went wrong",
                          message=str(exc.detail or "Please go back and try again."))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": 422, "message": "Invalid request parameters.",
                                 "details": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]},
                                status_code=422)
        with get_engine().connect() as conn:
            return render(request, "public/error.html", conn, status_code=400, page_title="Check your request",
                          heading="Something in that request wasn't valid",
                          message="Go back, check what you entered, and try again.")

    return app
