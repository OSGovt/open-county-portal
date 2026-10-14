"""Draw a demonstration page image on demand.

Generated documents have image rows whose path is "_synthetic/<instrument>/<seq>".
Page 1 is drawn from the page's stored text, so what the image shows and what
"machine-read text" shows are the same. Later pages show the stored line plus
grey bars standing in for body text. Drawing is deterministic.
"""
from __future__ import annotations

import random

from PIL import Image, ImageDraw

SYNTHETIC_DIR = "_synthetic"
WIDTH, HEIGHT = 1275, 1650


def is_synthetic(path) -> bool:
    parts = str(path).replace("\\", "/").split("/")
    return SYNTHETIC_DIR in parts


def _key(path) -> tuple[str, int]:
    parts = str(path).replace("\\", "/").split("/")
    i = parts.index(SYNTHETIC_DIR)
    return parts[i + 1], int(parts[i + 2])


def render(path) -> Image.Image:
    from sqlalchemy import select

    from ..db import get_engine, images, instruments
    from ..images import _font
    number, seq = _key(path)
    with get_engine().connect() as conn:
        row = conn.execute(select(images.c.ocr_text, instruments.c.page_count)
                           .select_from(images.join(instruments, instruments.c.id == images.c.instrument_id))
                           .where(instruments.c.instrument_number == number, images.c.seq == seq)).first()
    text = (row.ocr_text if row else "") or ""
    pages = row.page_count if row else 1
    img = Image.new("L", (WIDTH, HEIGHT), 250)
    d = ImageDraw.Draw(img)
    rng = random.Random(f"{number}/{seq}")
    small, body, big = _font(22), _font(26), _font(40)
    d.text((80, 50), "SAMPLE DOCUMENT - FICTIONAL - NOT A REAL RECORD", fill=110, font=small)
    d.text((WIDTH - 420, 50), f"{number}   page {seq} of {pages}", fill=110, font=small)
    y = 130
    lines = text.splitlines()
    if seq == 1 and lines:
        d.text((80, y), lines[0], fill=0, font=big)
        y += 80
        for line in lines[1:]:
            for chunk in _wrap(line, 78):
                d.text((80, y), chunk, fill=20, font=body)
                y += 40
            y += 8
        y += 30
    else:
        for line in lines[:2]:
            d.text((80, y), line, fill=20, font=body)
            y += 44
        y += 20
    # Grey bars where body text, signatures and the notary block would be.
    bottom = HEIGHT - 340 if seq == pages else HEIGHT - 200
    while y < bottom:
        width = rng.randint(820, 1110) if rng.random() > 0.12 else rng.randint(300, 700)
        d.rectangle([80, y, 80 + width, y + 14], fill=rng.randint(195, 215))
        y += 34 if rng.random() > 0.15 else 60
    if seq == pages:
        d.line([(80, HEIGHT - 190), (560, HEIGHT - 190)], fill=60, width=2)
        d.text((80, HEIGHT - 180), "Signature (sample)", fill=90, font=small)
        d.ellipse([WIDTH - 330, HEIGHT - 300, WIDTH - 110, HEIGHT - 80], outline=120, width=3)
        d.text((WIDTH - 300, HEIGHT - 200), "SAMPLE SEAL", fill=120, font=small)
    return img


def _wrap(line: str, width: int) -> list[str]:
    words, out, cur = line.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out or [""]
