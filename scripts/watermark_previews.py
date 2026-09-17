#!/usr/bin/env python3
"""Bake PartsHarbor preview watermarks into kit preview PNGs.

Clean sources live in scripts/preview-sources/ (not served by GitHub Pages).
Watermarked outputs are written to docs/assets/previews/.

Regenerate previews from kit PDFs or edit sources, then run:
  python3 scripts/watermark_previews.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "scripts" / "preview-sources"
OUTPUT_DIR = ROOT / "docs" / "assets" / "previews"
WATERMARK_TEXT = "PartsHarbor · Preview"
FILL = (12, 18, 34, 72)  # navy, ~28% alpha on white backgrounds


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _make_tile(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> Image.Image:
    probe = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 36, 28
    tile = Image.new("RGBA", (text_w + pad_x * 2, text_h + pad_y * 2), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)
    tile_draw.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=font, fill=FILL)
    return tile.rotate(-35, expand=True, resample=Image.Resampling.BICUBIC)


def watermark_image(source: Path, destination: Path) -> None:
    base = Image.open(source).convert("RGBA")
    width, height = base.size
    font_size = max(22, min(width, height) // 22)
    font = _load_font(font_size)
    tile = _make_tile(WATERMARK_TEXT, font)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    step_x = max(tile.width, int(tile.width * 0.72))
    step_y = max(tile.height, int(tile.height * 0.72))
    offset_x = -tile.width // 2
    offset_y = -tile.height // 2

    y = offset_y
    row = 0
    while y < height + tile.height:
        x = offset_x + (step_x // 3 if row % 2 else 0)
        while x < width + tile.width:
            overlay.alpha_composite(tile, (x, y))
            x += step_x
        y += step_y
        row += 1

    # One larger center mark for screenshots that crop tightly.
    center_tile = _make_tile(WATERMARK_TEXT, _load_font(int(font_size * 1.35)))
    cx = (width - center_tile.width) // 2
    cy = (height - center_tile.height) // 2
    overlay.alpha_composite(center_tile, (cx, cy))

    result = Image.alpha_composite(base, overlay).convert("RGB")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.save(destination, format="PNG", optimize=True)
    print(f"watermarked {destination.relative_to(ROOT)}")


def main() -> None:
    previews = sorted(SOURCE_DIR.glob("*.png"))
    if not previews:
        raise SystemExit(f"No PNG sources found in {SOURCE_DIR}")

    for source in previews:
        watermark_image(source, OUTPUT_DIR / source.name)


if __name__ == "__main__":
    main()
