"""Document page images: rendering, redaction, PDF assembly and OCR.

Original images are never modified. Redactions are stored as rectangles and
painted over a rendered copy every time a page is shown or downloaded, so the
official record stays intact and every redaction is reversible and logged.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .settings import get_settings

MAX_WIDTH = 1700
Image.MAX_IMAGE_PIXELS = 300_000_000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def open_frame(path: Path, frame: int = 0) -> Image.Image:
    img = Image.open(path)
    if frame:
        img.seek(frame)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("1", "P", "CMYK", "I;16", "I", "F", "LA", "RGBA"):
        img = img.convert("RGB") if img.mode in ("P", "CMYK", "RGBA", "LA") else img.convert("L")
    return img


def frame_count(path: Path) -> int:
    with Image.open(path) as img:
        return getattr(img, "n_frames", 1)


def render_page(path: Path, frame: int, marks: list[dict]) -> bytes:
    """PNG bytes for one page with redaction boxes painted solid black."""
    img = open_frame(path, frame)
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)
    if marks:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        for m in marks:
            x0 = img.width * m["x"] / 1000
            y0 = img.height * m["y"] / 1000
            x1 = x0 + img.width * m["w"] / 1000
            y1 = y0 + img.height * m["h"] / 1000
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def cached_page(image_row: dict, marks: list[dict]) -> bytes:
    settings = get_settings()
    key = hashlib.sha256(repr((image_row["id"], image_row["sha256"], image_row["frame"],
                               sorted((m["x"], m["y"], m["w"], m["h"]) for m in marks))).encode()).hexdigest()
    cache = settings.cache_dir / "pages" / key[:2] / f"{key}.png"
    if cache.exists():
        return cache.read_bytes()
    data = render_page(settings.images_dir / image_row["path"], image_row["frame"], marks)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(cache)
    return data


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def text_page(lines: list[str], width: int = 1700, height: int = 2200) -> Image.Image:
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    y = 140
    for i, line in enumerate(lines):
        font = _font(54 if i == 0 else 36)
        draw.text((140, y), line, fill="black", font=font)
        y += 90 if i == 0 else 60
    return page


def assemble_pdf(page_pngs: list[bytes], cover_lines: list[str] | None = None) -> bytes:
    pages = []
    if cover_lines:
        pages.append(text_page(cover_lines))
    for data in page_pngs:
        pages.append(Image.open(io.BytesIO(data)).convert("RGB"))
    if not pages:
        pages.append(text_page(["No page images are available for this document."]))
    out = io.BytesIO()
    pages[0].save(out, format="PDF", save_all=True, append_images=pages[1:], resolution=200.0)
    return out.getvalue()


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr(path: Path, frame: int = 0) -> str:
    """Machine-read text for one page using Tesseract, if it is installed."""
    if not ocr_available():
        return ""
    img = open_frame(path, frame)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    proc = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "3"], input=buf.getvalue(),
                          capture_output=True, timeout=180)
    return proc.stdout.decode("utf-8", "replace").strip()


def pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int = 200) -> list[Path]:
    """Split a PDF into one PNG per page (needs poppler's pdftoppm)."""
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm (poppler-utils) is required to import PDF document images.")
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf.stem
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)], check=True, timeout=600)
    return sorted(out_dir.glob(f"{pdf.stem}*.png"))
