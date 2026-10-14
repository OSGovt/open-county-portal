"""Theme engine: brand colors in, accessible CSS out.

An administrator picks colors (or imports them from the old site). Before
anything is published, every color pairing the site uses is checked against
WCAG 2.1 contrast minimums. A color that fails is moved lighter or darker,
keeping its hue, until it passes, and the administrator is told exactly what
changed. A theme that fails cannot be published.
"""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field

HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")

DEFAULT_THEME: dict = {
    "colors": {
        "primary": "#0B5563",
        "header_bg": "#0B3C47",
        "header_text": "#FFFFFF",
        "background": "#F6F4EF",
        "surface": "#FFFFFF",
        "text": "#16232E",
        "muted": "#4A5866",
        "link": "#0B5563",
        "border": "#5B6875",
        "alert_bg": "#FFF4E5",
        "alert_text": "#6B3304",
        "success_bg": "#E7F4EC",
        "success_text": "#134A27",
        "error": "#B42318",
        "focus": "#C77700",
        "footer_bg": "#16232E",
        "footer_text": "#FFFFFF",
    },
    "font": "system",
    "font_family_custom": "",
    "font_css_url": "",
    "base_size": 17,
    "radius": 6,
    "logo_file_id": None,
    "logo_alt": "",
    "show_name_with_logo": True,
}

FONT_STACKS = {
    "system": "system-ui, -apple-system, 'Segoe UI', 'Noto Sans', 'Liberation Sans', sans-serif",
    "humanist": "'Seravek', 'Gill Sans Nova', 'Ubuntu', 'Calibri', 'DejaVu Sans', source-sans-pro, sans-serif",
    "serif": "'Iowan Old Style', 'Palatino Linotype', 'URW Palladio L', P052, 'Georgia', serif",
    "readable": "'Atkinson Hyperlegible', 'Verdana', 'DejaVu Sans', sans-serif",
}

# (foreground key, background key, minimum ratio, plain-English description)
PAIRS: list[tuple[str, str, float, str]] = [
    ("text", "background", 4.5, "Body text on the page background"),
    ("text", "surface", 4.5, "Body text on cards and forms"),
    ("muted", "background", 4.5, "Secondary text on the page background"),
    ("muted", "surface", 4.5, "Secondary text on cards"),
    ("link", "background", 4.5, "Links on the page background"),
    ("link", "surface", 4.5, "Links on cards"),
    ("primary", "surface", 4.5, "Outline button text on cards"),
    ("header_text", "header_bg", 4.5, "Header text on the header"),
    ("footer_text", "footer_bg", 4.5, "Footer text on the footer"),
    ("alert_text", "alert_bg", 4.5, "Alert banner text"),
    ("success_text", "success_bg", 4.5, "Confirmation message text"),
    ("error", "surface", 4.5, "Error messages on forms"),
    ("error", "background", 4.5, "Error messages on the page"),
    ("border", "surface", 3.0, "Form field borders (WCAG 1.4.11)"),
    ("focus", "background", 3.0, "Keyboard focus ring on the page (WCAG 1.4.11)"),
    ("focus", "surface", 3.0, "Keyboard focus ring on cards"),
    ("focus", "header_bg", 3.0, "Keyboard focus ring in the header"),
]


def normalize_hex(value: str) -> str:
    m = HEX.match(value.strip())
    if not m:
        raise ValueError(f"'{value}' is not a color. Use a hex color like #0B5563.")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = normalize_hex(hex_color)[1:]
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def luminance(hex_color: str) -> float:
    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_color)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def shift_until(fg: str, bg: str, minimum: float) -> str:
    """Move fg's lightness away from bg, keeping hue, until contrast >= minimum."""
    if contrast(fg, bg) >= minimum:
        return normalize_hex(fg)
    r, g, b = _rgb(fg)
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    darker = luminance(bg) > 0.18
    for _ in range(200):
        light = max(0.0, light - 0.005) if darker else min(1.0, light + 0.005)
        candidate = _hex(colorsys.hls_to_rgb(h, light, s))
        if contrast(candidate, bg) >= minimum:
            return candidate
        if light in (0.0, 1.0):
            break
    return "#000000" if darker else "#FFFFFF"


def text_on(bg: str) -> str:
    """Pick white or near-black text, whichever reads better on bg."""
    white, ink = "#FFFFFF", "#111111"
    return white if contrast(white, bg) >= contrast(ink, bg) else ink


def darken(hex_color: str, amount: float) -> str:
    r, g, b = _rgb(hex_color)
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    return _hex(colorsys.hls_to_rgb(h, max(0.0, light - amount), s))


def mix(a: str, b: str, weight: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x * weight + y * (1 - weight) for x, y in zip(ra, rb)))  # type: ignore[arg-type]


@dataclass
class Check:
    description: str
    fg: str
    bg: str
    ratio: float
    minimum: float

    @property
    def passed(self) -> bool:
        return self.ratio >= self.minimum


@dataclass
class ThemeResult:
    theme: dict
    checks: list[Check]
    changes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


def merged(theme: dict | None) -> dict:
    out = {**DEFAULT_THEME, **(theme or {})}
    out["colors"] = {**DEFAULT_THEME["colors"], **((theme or {}).get("colors") or {})}
    return out


def check(theme: dict) -> list[Check]:
    c = merged(theme)["colors"]
    out = [Check(desc, c[f], c[b], round(contrast(c[f], c[b]), 2), m) for f, b, m, desc in PAIRS]
    on_primary = text_on(c["primary"])
    out.append(Check("Button text on filled buttons", on_primary, c["primary"],
                     round(contrast(on_primary, c["primary"]), 2), 4.5))
    return out


def validate_and_fix(theme: dict) -> ThemeResult:
    """Normalize colors, repair any pairing below minimum, and report changes."""
    t = merged(theme)
    colors = {}
    for key, value in t["colors"].items():
        colors[key] = normalize_hex(value)
    t["colors"] = colors
    changes: list[str] = []
    for _ in range(3):  # a fix to one pair can affect another; settle in a few passes
        for fg, bg, minimum, desc in PAIRS:
            before = colors[fg]
            if fg in ("header_text", "footer_text") and contrast(before, colors[bg]) < minimum \
                    and contrast(text_on(colors[bg]), colors[bg]) >= minimum:
                after = text_on(colors[bg])
            else:
                after = shift_until(before, colors[bg], minimum)
            if after != before:
                colors[fg] = after
                changes.append(f"{desc}: changed {fg.replace('_', ' ')} from {before} to {after} "
                               f"so it reaches {minimum}:1 contrast.")
        on_primary = text_on(colors["primary"])
        if contrast(on_primary, colors["primary"]) < 4.5:
            before = colors["primary"]
            colors["primary"] = shift_until(before, on_primary, 4.5)
            changes.append(f"Filled buttons: changed primary from {before} to {colors['primary']} "
                           f"so button text reaches 4.5:1.")
    t["base_size"] = max(16, min(22, int(t.get("base_size") or 17)))
    t["radius"] = max(0, min(16, int(t.get("radius") or 0)))
    if t.get("font") not in FONT_STACKS and t.get("font") != "custom":
        t["font"] = "system"
    if t.get("font_css_url") and not str(t["font_css_url"]).startswith("https://"):
        t["font_css_url"] = ""
        changes.append("Removed the font stylesheet address because it did not start with https://.")
    # Deduplicate change notes while keeping order.
    seen, unique = set(), []
    for line in changes:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return ThemeResult(theme=t, checks=check(t), changes=unique)


def font_stack(theme: dict) -> str:
    t = merged(theme)
    if t.get("font") == "custom" and t.get("font_family_custom"):
        safe = re.sub(r"[^A-Za-z0-9 ,'\-]", "", t["font_family_custom"])
        return f"{safe}, {FONT_STACKS['system']}"
    return FONT_STACKS.get(t.get("font", "system"), FONT_STACKS["system"])


def css_variables(theme: dict) -> str:
    t = merged(theme)
    c = t["colors"]
    lines = [f"  --c-{k.replace('_', '-')}: {v};" for k, v in c.items()]
    lines += [
        f"  --c-on-primary: {text_on(c['primary'])};",
        f"  --c-primary-hover: {darken(c['primary'], 0.08)};",
        f"  --c-primary-soft: {mix(c['primary'], c['surface'], 0.10)};",
        f"  --c-rule: {mix(c['text'], c['surface'], 0.18)};",
        f"  --font-body: {font_stack(t)};",
        f"  --base-size: {t['base_size']}px;",
        f"  --radius: {t['radius']}px;",
    ]
    return ":root {\n" + "\n".join(lines) + "\n}\n"


def import_colors_from_css(css_text: str) -> dict:
    """Suggest a theme from an old site's CSS: the most-used non-neutral color
    becomes the primary. The result is then run through validate_and_fix."""
    counts: dict[str, int] = {}
    for m in re.finditer(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", css_text):
        try:
            hexed = normalize_hex(m.group(0))
        except ValueError:
            continue
        r, g, b = _rgb(hexed)
        _, light, sat = colorsys.rgb_to_hls(r, g, b)
        if sat < 0.18 or light > 0.92 or light < 0.08:
            continue  # skip greys, near-white, near-black
        counts[hexed] = counts.get(hexed, 0) + 1
    if not counts:
        return {}
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0]
    colors = {"primary": primary, "link": primary, "header_bg": darken(primary, 0.12)}
    colors["header_text"] = text_on(colors["header_bg"])
    if len(ranked) > 1:
        colors["focus"] = ranked[1][0]
    return {"colors": colors}
