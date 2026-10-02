"""Raster app icons from the logo geometry (rounded square + square-wave), drawn with Pillow.

    python scripts/make_icons.py
Writes docs/img/icon-*.png (installable web app) and desktop/src-tauri/icons/source-1024.png
plus every desktop icon tauri.conf.json lists (png, ico, icns).
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
GREEN, WHITE = (29, 107, 79, 255), (255, 255, 255, 255)
WAVE = [(6, 21), (11, 21), (11, 11), (16, 11), (16, 21), (21, 21), (21, 11), (26, 11)]


def draw(size: int, maskable: bool = False) -> Image.Image:
    ss = 4  # supersample, then downscale for clean edges
    n = size * ss
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if maskable:  # full-bleed background, logo inside the 80% safe zone
        d.rectangle([0, 0, n, n], fill=GREEN)
        k, off = n * 0.70 / 32, n * 0.15
    else:
        k, off = n / 32, 0.0
        d.rounded_rectangle([off + 1 * k, off + 1 * k, off + 31 * k, off + 31 * k], radius=7 * k, fill=GREEN)
    pts = [(off + x * k, off + y * k) for x, y in WAVE]
    w = max(1, round(2.4 * k))
    d.line(pts, fill=WHITE, width=w, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=WHITE)
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    img = ROOT / "docs" / "img"
    draw(192).save(img / "icon-192.png")
    draw(512).save(img / "icon-512.png")
    draw(512, maskable=True).save(img / "icon-maskable-512.png")
    draw(180, maskable=True).convert("RGB").save(img / "apple-touch-icon.png")
    out = ROOT / "desktop" / "src-tauri" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    big = draw(1024)
    big.save(out / "source-1024.png")
    # the exact files tauri.conf.json lists, so the desktop build needs no extra tooling
    draw(32).save(out / "32x32.png")
    draw(128).save(out / "128x128.png")
    draw(256).save(out / "128x128@2x.png")
    draw(256).save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(out / "icon.icns")
    big.save(out / "icon.png")
    print("icons written")
