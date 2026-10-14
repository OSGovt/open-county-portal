"""Settings: site identity, alert, theme, payments, records, open data,
staff accounts, API keys and custom forms."""
from __future__ import annotations

import hashlib
import re
import secrets
import urllib.parse

import httpx
import yaml
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from starlette.datastructures import UploadFile

from ... import auth, config_store, payments, statepacks, theme as theme_mod
from ...db import api_keys, audit, files, get_engine, offices, tx, users
from ...web import flash, parse_money, verify_csrf
from .common import staff_render
from .content import _save_file

router = APIRouter(prefix="/settings")

SITE_FIELDS = [
    ("jurisdiction_name", "Name of the county or district", "text", "Shown in the header and page titles."),
    ("tagline", "Tagline (optional)", "text", ""),
    ("address", "Main address", "textarea", "Shown in the footer."),
    ("phone", "Main phone", "text", ""),
    ("email", "Main email", "text", ""),
    ("accessibility_contact", "How to report an accessibility barrier", "textarea",
     "A name, phone and email. Shown on the Accessibility page."),
    ("appraisal_district_url", "Appraisal district website", "text", "Linked from the property tax pages."),
    ("population", "Population (latest census)", "text", "Sets your federal accessibility deadline."),
    ("census_government_id", "Census Bureau government ID", "text", "Used in the national directory."),
    ("fips", "County FIPS code (5 digits)", "text", ""),
    ("timezone", "Time zone", "text", "For example: America/Chicago"),
]


@router.get("")
def index(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        return staff_render(request, "staff/settings_index.html", conn, user, page_title="Settings")


# ---- site identity and alert -------------------------------------------------------

@router.get("/site")
def site_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        return staff_render(request, "staff/settings_site.html", conn, user, page_title="Site identity",
                            fields=SITE_FIELDS, values=config_store.get(conn, "site"),
                            alert_values=config_store.get(conn, "alert"), packs=statepacks.available())


@router.post("/site", dependencies=[Depends(verify_csrf)])
async def site_save(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        site = config_store.get(conn, "site")
        for name, *_ in SITE_FIELDS:
            site[name] = str(form.get(name, "")).strip()
        if not site["jurisdiction_name"]:
            flash(request, "The name can't be blank.", "error")
            return RedirectResponse("/staff/settings/site", status_code=303)
        site["population"] = int(re.sub(r"\D", "", site["population"])) if re.sub(r"\D", "", site["population"] or "") else None
        config_store.put(conn, "site", site, actor=user["email"])
        audit(conn, user["email"], "settings.site")
    flash(request, "Site identity saved.")
    return RedirectResponse("/staff/settings/site", status_code=303)


@router.post("/alert", dependencies=[Depends(verify_csrf)])
async def alert_save(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "admin", "content")
        alert = {"enabled": form.get("enabled") == "on", "level": "warning",
                 "title": str(form.get("title", "")).strip(), "body": str(form.get("body", "")).strip(),
                 "link_text": str(form.get("link_text", "")).strip(), "link_url": str(form.get("link_url", "")).strip()}
        if alert["enabled"] and not alert["title"]:
            flash(request, "Give the alert a short title.", "error")
            return RedirectResponse("/staff/settings/site#alert", status_code=303)
        config_store.put(conn, "alert", alert, actor=user["email"])
        audit(conn, user["email"], "settings.alert", detail={"enabled": alert["enabled"]})
    flash(request, "Alert banner " + ("is showing on every page." if alert["enabled"] else "is off."))
    return RedirectResponse("/staff/settings/site#alert", status_code=303)


# ---- theme ----------------------------------------------------------------------

def _theme_from_form(form, current: dict) -> dict:
    t = theme_mod.merged(current)
    for key in theme_mod.DEFAULT_THEME["colors"]:
        v = str(form.get(f"c_{key}", "")).strip()
        if v:
            t["colors"][key] = v
    for key in ("font", "font_family_custom", "font_css_url", "logo_alt"):
        if key in form:
            t[key] = str(form.get(key, "")).strip()
    for key in ("base_size", "radius"):
        if str(form.get(key, "")).strip().isdigit():
            t[key] = int(form.get(key))
    t["show_name_with_logo"] = form.get("show_name_with_logo") == "on"
    return t


@router.get("/theme")
def theme_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        current = theme_mod.merged(config_store.get(conn, "theme") or {})
        proposal = request.session.get("theme_proposal")
        shown = theme_mod.merged(proposal) if proposal else current
        result = theme_mod.validate_and_fix(shown)
        return staff_render(request, "staff/settings_theme.html", conn, user, page_title="Theme", t=shown, result=result,
                            proposal=bool(proposal), history=config_store.history(conn, "theme", 20),
                            fonts=theme_mod.FONT_STACKS, labels=_color_labels())


def _color_labels():
    return {"primary": "Buttons and accents", "header_bg": "Header background", "header_text": "Header text",
            "background": "Page background", "surface": "Cards and forms", "text": "Body text",
            "muted": "Secondary text", "link": "Links", "border": "Form field borders", "alert_bg": "Alert background",
            "alert_text": "Alert text", "success_bg": "Confirmation background", "success_text": "Confirmation text",
            "error": "Errors", "focus": "Keyboard focus ring", "footer_bg": "Footer background", "footer_text": "Footer text"}


@router.post("/theme", dependencies=[Depends(verify_csrf)])
async def theme_action(request: Request):
    form = await request.form()
    action = form.get("action")
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        current = config_store.get(conn, "theme") or {}
        if action == "discard":
            request.session.pop("theme_proposal", None)
            flash(request, "Preview discarded.")
            return RedirectResponse("/staff/settings/theme", status_code=303)
        if action == "restore":
            config_store.restore(conn, "theme", int(form.get("history_id", 0)), user["email"])
            request.session.pop("theme_proposal", None)
            audit(conn, user["email"], "theme.restore", detail={"history_id": form.get("history_id")})
            flash(request, "Earlier theme restored and published.")
            return RedirectResponse("/staff/settings/theme", status_code=303)
        base = request.session.get("theme_proposal") or current
        try:
            proposal = _theme_from_form(form, base)
            result = theme_mod.validate_and_fix(proposal)
        except ValueError as exc:
            flash(request, str(exc), "error")
            return RedirectResponse("/staff/settings/theme", status_code=303)
        up = form.get("logo")
        if isinstance(up, UploadFile) and up.filename:
            if not up.filename.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".webp")):
                flash(request, "Upload the logo as PNG, JPG, SVG or WEBP.", "error")
                return RedirectResponse("/staff/settings/theme", status_code=303)
            meta = await _save_file(up, user["email"])
            meta["needs_accessibility_review"] = False
            result.theme["logo_file_id"] = conn.execute(files.insert().values(**meta).returning(files.c.id)).scalar_one()
            if not result.theme.get("logo_alt"):
                result.theme["logo_alt"] = config_store.get(conn, "site")["jurisdiction_name"] + " logo"
        if form.get("remove_logo") == "on":
            result.theme["logo_file_id"] = None
        if action == "publish":
            config_store.put(conn, "theme", result.theme, actor=user["email"],
                             note="; ".join(result.changes)[:300] if result.changes else None)
            request.session.pop("theme_proposal", None)
            audit(conn, user["email"], "theme.publish", detail={"changes": result.changes})
            msg = "Theme published to the live site."
            if result.changes:
                msg += f" {len(result.changes)} color(s) were adjusted to meet contrast rules; see the list below."
            flash(request, msg)
        else:
            request.session["theme_proposal"] = result.theme
            flash(request, "Preview ready. Open the preview, then publish if you like it." +
                  (f" {len(result.changes)} color(s) were adjusted for contrast." if result.changes else ""))
    return RedirectResponse("/staff/settings/theme", status_code=303)


@router.get("/theme/preview.css")
def theme_preview_css(request: Request):
    proposal = request.session.get("theme_proposal")
    with get_engine().connect() as conn:
        auth.require(request, conn, "admin")
        t = proposal or config_store.get(conn, "theme") or {}
    return Response(theme_mod.css_variables(theme_mod.merged(t)), media_type="text/css", headers={"Cache-Control": "no-store"})


@router.get("/theme/preview")
def theme_preview(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        return staff_render(request, "staff/theme_preview.html", conn, user, page_title="Theme preview")


@router.post("/theme/import", dependencies=[Depends(verify_csrf)])
async def theme_import(request: Request):
    """Suggest colors from the old website so the new one feels familiar."""
    form = await request.form()
    url = str(form.get("url", "")).strip()
    with get_engine().connect() as conn:
        auth.require(request, conn, "admin")
    if not url.startswith(("http://", "https://")):
        flash(request, "Enter the old site's full address, starting with https://", "error")
        return RedirectResponse("/staff/settings/theme", status_code=303)
    try:
        css_text, logo = _fetch_site_css(url)
    except Exception as exc:
        flash(request, f"Couldn't read {url}: {exc.__class__.__name__}. Check the address, or enter colors by hand.", "error")
        return RedirectResponse("/staff/settings/theme", status_code=303)
    suggestion = theme_mod.import_colors_from_css(css_text)
    if not suggestion:
        flash(request, "No brand colors were found on that site. Enter colors by hand.", "warning")
        return RedirectResponse("/staff/settings/theme", status_code=303)
    with get_engine().connect() as conn:
        base = request.session.get("theme_proposal") or config_store.get(conn, "theme") or {}
    proposal = theme_mod.merged(base)
    proposal["colors"].update(suggestion["colors"])
    result = theme_mod.validate_and_fix(proposal)
    request.session["theme_proposal"] = result.theme
    msg = "Colors imported from the old site as a preview. Nothing is published yet."
    if logo:
        msg += f" A possible logo was found at {logo}; download it and upload it below if it's right."
    flash(request, msg)
    return RedirectResponse("/staff/settings/theme", status_code=303)


def _fetch_site_css(url: str) -> tuple[str, str | None]:
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "OpenCountyPortal theme import"}) as client:
        page = client.get(url)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        chunks = [s.get_text() for s in soup.find_all("style")]
        chunks += [str(tag.get("style")) for tag in soup.find_all(style=True)]
        for link in soup.find_all("link", rel=lambda r: r and "stylesheet" in r)[:10]:
            href = link.get("href")
            if href:
                try:
                    r = client.get(urllib.parse.urljoin(url, href))
                    if r.status_code == 200 and len(r.content) < 3_000_000:
                        chunks.append(r.text)
                except httpx.HTTPError:
                    continue
        logo = None
        for im in soup.find_all("img"):
            hay = " ".join([im.get("src", ""), im.get("alt", ""), " ".join(im.get("class", []))]).lower()
            if "logo" in hay or "seal" in hay:
                logo = urllib.parse.urljoin(url, im.get("src", ""))
                break
    return "\n".join(chunks), logo


# ---- payments, records, open data ---------------------------------------------

@router.get("/payments")
def payments_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        office_rows = conn.execute(select(offices).order_by(offices.c.sort)).mappings().all()
        return staff_render(request, "staff/settings_payments.html", conn, user, page_title="Payments",
                            p=config_store.get(conn, "payments"), adapters=payments.installed(), office_rows=office_rows,
                            r=config_store.get(conn, "records"), od=config_store.get(conn, "open_data"))


@router.post("/payments", dependencies=[Depends(verify_csrf)])
async def payments_save(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        p = config_store.get(conn, "payments")
        processor = str(form.get("processor", "test"))
        if processor not in payments.installed():
            raise HTTPException(400)
        p["processor"] = processor
        p["methods"] = [m for m in ("card", "wallet", "ach") if form.get(f"m_{m}") == "on"] or ["card"]
        if processor == "stripe" and "ach" in p["methods"]:
            p["methods"].remove("ach")
            p["methods"] = p["methods"] or ["card"]
            flash(request, "eCheck was turned off: the Stripe adapter supports cards and wallets only.", "warning")
        try:
            p["card_fee_percent"] = float(str(form.get("card_fee_percent", "0")).strip() or 0)
        except ValueError:
            flash(request, "Enter the card fee percentage as a number, like 2.5", "error")
            return RedirectResponse("/staff/settings/payments", status_code=303)
        p["card_fee_flat_cents"] = parse_money(str(form.get("card_fee_flat", ""))) or 0
        p["card_fee_min_cents"] = parse_money(str(form.get("card_fee_min", ""))) or 0
        p["ach_fee_flat_cents"] = parse_money(str(form.get("ach_fee_flat", ""))) or 0
        p["fee_authority"] = str(form.get("fee_authority", "")).strip()
        secrets_text = str(form.get("processor_settings", "")).strip()
        if secrets_text and not secrets_text.startswith("(unchanged"):
            try:
                parsed = yaml.safe_load(secrets_text)
                if not isinstance(parsed, dict):
                    raise ValueError
                p["processor_settings"] = parsed
            except (yaml.YAMLError, ValueError):
                flash(request, "Processor settings must be lines of 'name: value'.", "error")
                return RedirectResponse("/staff/settings/payments", status_code=303)
        config_store.put(conn, "payments", p, actor=user["email"])
        for o in conn.execute(select(offices.c.slug)).scalars():
            if f"merchant_{o}" in form:
                conn.execute(offices.update().where(offices.c.slug == o)
                             .values(merchant_account=str(form.get(f"merchant_{o}", "")).strip() or None))
        r = config_store.get(conn, "records")
        r["free_downloads"] = form.get("free_downloads") == "on"
        r["show_property_id"] = form.get("show_property_id") == "on"
        config_store.put(conn, "records", r, actor=user["email"])
        od = config_store.get(conn, "open_data")
        for k in ("data_terms", "license_url", "contact_name", "contact_email"):
            od[k] = str(form.get(k, "")).strip()
        config_store.put(conn, "open_data", od, actor=user["email"])
        audit(conn, user["email"], "settings.payments", detail={"processor": processor})
    flash(request, "Payment, records and open data settings saved.")
    return RedirectResponse("/staff/settings/payments", status_code=303)


# ---- staff accounts -------------------------------------------------------------

@router.get("/users")
def users_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        rows = conn.execute(select(users).order_by(users.c.active.desc(), users.c.name)).mappings().all()
        office_rows = conn.execute(select(offices.c.slug, offices.c.name).order_by(offices.c.sort)).all()
        new_password = request.session.pop("new_user_password", None)
        return staff_render(request, "staff/settings_users.html", conn, user, page_title="Staff accounts", rows=rows,
                            roles=auth.ROLES, office_rows=office_rows, new_password=new_password)


@router.post("/users", dependencies=[Depends(verify_csrf)])
async def users_action(request: Request):
    form = await request.form()
    action = form.get("action")
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        roles = [r for r in form.getlist("roles") if r in auth.ROLES]
        offices_sel = list(form.getlist("offices"))
        if action == "add":
            email, name = str(form.get("email", "")).strip(), str(form.get("name", "")).strip()
            if "@" not in email or not name:
                flash(request, "Enter the person's name and work email.", "error")
                return RedirectResponse("/staff/settings/users", status_code=303)
            try:
                temp = auth.create_user(conn, email, name, roles, offices_sel, actor=user["email"])
            except ValueError as exc:
                flash(request, str(exc), "error")
                return RedirectResponse("/staff/settings/users", status_code=303)
            request.session["new_user_password"] = {"email": email, "password": temp}
            flash(request, f"Account created for {name}.")
        elif action in ("update", "reset", "disable", "enable"):
            uid = int(form.get("user_id", 0))
            target = conn.execute(select(users).where(users.c.id == uid)).mappings().first()
            if target is None:
                raise HTTPException(404)
            if target["id"] == user["id"] and action == "disable":
                flash(request, "You can't disable your own account.", "error")
                return RedirectResponse("/staff/settings/users", status_code=303)
            if action == "update":
                if target["id"] == user["id"] and "admin" not in roles:
                    flash(request, "You can't remove your own administrator role.", "error")
                    return RedirectResponse("/staff/settings/users", status_code=303)
                conn.execute(users.update().where(users.c.id == uid).values(roles=roles, offices=offices_sel))
                flash(request, f"Saved roles for {target['name']}.")
            elif action == "reset":
                temp = auth.temporary_password()
                conn.execute(users.update().where(users.c.id == uid).values(
                    password_hash=auth.hash_password(temp), must_change_password=True, mfa_enrolled=False,
                    totp_secret=auth.new_totp_secret(), failed_logins=0, locked_until=None))
                request.session["new_user_password"] = {"email": target["email"], "password": temp}
                flash(request, f"{target['name']} will set a new password and phone code at next sign-in.")
            else:
                conn.execute(users.update().where(users.c.id == uid).values(active=(action == "enable")))
                flash(request, f"{target['name']} {'re-enabled' if action == 'enable' else 'disabled'}.")
            audit(conn, user["email"], f"user.{action}", "user", target["email"], {"roles": roles})
    return RedirectResponse("/staff/settings/users", status_code=303)


# ---- API keys --------------------------------------------------------------------

@router.get("/api-keys")
def keys_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        rows = conn.execute(select(api_keys).order_by(api_keys.c.created_at.desc())).mappings().all()
        return staff_render(request, "staff/settings_keys.html", conn, user, page_title="API keys", rows=rows,
                            new_key=request.session.pop("new_api_key", None))


@router.post("/api-keys", dependencies=[Depends(verify_csrf)])
async def keys_action(request: Request):
    form = await request.form()
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        if form.get("action") == "create":
            key = "ocp_" + secrets.token_urlsafe(24)
            conn.execute(api_keys.insert().values(key_hash=hashlib.sha256(key.encode()).hexdigest(),
                                                  label=str(form.get("label", "")).strip() or "Unnamed",
                                                  email=str(form.get("email", "")).strip() or None))
            request.session["new_api_key"] = key
            audit(conn, user["email"], "apikey.create", detail={"label": form.get("label")})
        elif form.get("action") == "revoke":
            conn.execute(api_keys.update().where(api_keys.c.id == int(form.get("key_id", 0))).values(active=False))
            audit(conn, user["email"], "apikey.revoke", "api_key", form.get("key_id"))
            flash(request, "Key revoked.")
    return RedirectResponse("/staff/settings/api-keys", status_code=303)


# ---- custom forms -----------------------------------------------------------------

@router.get("/forms")
def forms_page(request: Request):
    with get_engine().connect() as conn:
        user = auth.require(request, conn, "admin")
        custom = config_store.get(conn, "forms_custom") or {}
        text = yaml.safe_dump(custom, sort_keys=False, allow_unicode=True) if custom else ""
        return staff_render(request, "staff/settings_forms.html", conn, user, page_title="Custom forms", text=text,
                            problems=[])


@router.post("/forms", dependencies=[Depends(verify_csrf)])
async def forms_save(request: Request):
    form = await request.form()
    text = str(form.get("forms", ""))
    with tx() as conn:
        user = auth.require(request, conn, "admin")
        try:
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise ValueError("The top level must be a list of form names.")
        except (yaml.YAMLError, ValueError) as exc:
            return staff_render(request, "staff/settings_forms.html", conn, user, status_code=400, page_title="Custom forms",
                                text=text, problems=[f"This isn't valid YAML: {exc}"])
        pack_stub = {k: [] for k in statepacks.REQUIRED_TOP}
        pack_stub.update({"pack": "x", "name": "x", "version": "x", "status": "x", "records": {}, "public_information": {},
                          "payments": {}, "forms": data,
                          "fees": [{"code": c, "office": "o", "label": c, "amount": 0, "statute": "x"}
                                   for c in {f.get("fee_code") for f in data.values() if isinstance(f, dict)} if c],
                          "offices": [{"slug": "o"}]})
        problems = [p for p in statepacks.validate(pack_stub) if p.startswith("form")]
        if problems:
            return staff_render(request, "staff/settings_forms.html", conn, user, status_code=400, page_title="Custom forms",
                                text=text, problems=problems)
        config_store.put(conn, "forms_custom", data, actor=user["email"])
        audit(conn, user["email"], "settings.forms", detail={"forms": list(data)})
    flash(request, f"Saved {len(data)} custom form(s). Each is at /apply/<form name>.")
    return RedirectResponse("/staff/settings/forms", status_code=303)
