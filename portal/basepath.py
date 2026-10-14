"""Serve the portal from a subfolder, such as https://www.example.org/utopia/.

Set PORTAL_BASE_PATH=/utopia (and PORTAL_SITE_URL to the full address including
it). Requests may arrive with or without the prefix: a front door that passes
/utopia/records through unchanged works, and so does one that strips it. Every
page, style sheet and redirect the portal sends back is rewritten so its own
links stay inside the subfolder. Templates keep writing plain "/records" links.
"""
from __future__ import annotations

import re

REWRITE_TYPES = (b"text/html", b"text/css")


class BasePathMiddleware:
    def __init__(self, app, base: str) -> None:
        self.app = app
        self.base = base
        b = re.escape(base)
        # href="/x" -> href="/utopia/x", but not "//cdn", not already-prefixed links
        self.attr = re.compile(r'((?:href|src|action|formaction)=["\'])/(?!/)(?!' + b[1:] + r'(?:/|["\']))')
        self.css = re.compile(r'(url\(\s*["\']?)/(?!/)(?!' + b[1:] + r'/)')

    def _prefix(self, value: str) -> str:
        if value.startswith("/") and not value.startswith("//") and not (
                value == self.base or value.startswith(self.base + "/")):
            return self.base + value
        return value

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not self.base:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == self.base or path.startswith(self.base + "/"):
            scope = dict(scope)
            scope["path"] = path[len(self.base):] or "/"
            raw = scope.get("raw_path")
            if raw:
                scope["raw_path"] = raw[len(self.base.encode()):] or b"/"
        state: dict = {"rewrite": False, "start": None, "chunks": []}

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                headers = []
                ctype = b""
                for k, v in message.get("headers", []):
                    lk = k.lower()
                    if lk == b"location":
                        v = self._prefix(v.decode("latin-1")).encode("latin-1")
                    elif lk == b"content-type":
                        ctype = v
                    headers.append((k, v))
                state["rewrite"] = any(ctype.startswith(t) for t in REWRITE_TYPES)
                if state["rewrite"]:
                    headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
                    state["start"] = {**message, "headers": headers}
                    return
                await send({**message, "headers": headers})
                return
            if message["type"] == "http.response.body" and state["rewrite"]:
                state["chunks"].append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = b"".join(state["chunks"]).decode("utf-8", "replace")
                body = self.attr.sub(lambda m: m.group(1) + self.base + "/", body)
                body = self.css.sub(lambda m: m.group(1) + self.base + "/", body)
                data = body.encode("utf-8")
                start = state["start"]
                start["headers"] = start["headers"] + [(b"content-length", str(len(data)).encode())]
                await send(start)
                await send({"type": "http.response.body", "body": data})
                return
            await send(message)

        await self.app(scope, receive, wrapped_send)
