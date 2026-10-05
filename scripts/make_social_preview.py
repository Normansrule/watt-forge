"""Render docs/img/social-preview.png (1280x640), the image GitHub shows when the repository
link is shared. Upload it once under Settings > General > Social preview (GitHub has no API
for this). Needs Playwright with Chromium: python -m pip install playwright.

    python scripts/make_social_preview.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def html() -> str:
    b = json.loads((ROOT / "data" / "control_benchmark.json").read_text())
    best = max(b["overall"].values(), key=lambda r: r["eta_mppt"])["eta_mppt"]
    logo = (DOCS / "img" / "favicon.svg").read_text()
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Inter; src: url("{(DOCS / 'fonts' / 'inter-latin-wght.woff2').as_uri()}"); font-weight: 100 900; }}
html, body {{ margin: 0; width: 1280px; height: 640px; }}
body {{ font-family: Inter, sans-serif; background: #f5f7f4; color: #15222b; display: grid; grid-template-columns: 1.05fr 1fr; }}
.l {{ padding: 64px 0 56px 72px; display: flex; flex-direction: column; }}
.brand {{ display: flex; align-items: center; gap: 18px; font-weight: 750; font-size: 40px; letter-spacing: -0.02em; }}
.brand svg {{ width: 64px; height: 64px; }}
h1 {{ font-size: 52px; line-height: 1.06; letter-spacing: -0.035em; margin: 34px 0 18px; font-weight: 750; }}
p {{ font-size: 23px; line-height: 1.45; color: #4b5a63; margin: 0; max-width: 560px; }}
.chips {{ margin-top: auto; display: flex; gap: 10px; flex-wrap: wrap; }}
.chip {{ font-size: 17px; font-weight: 600; padding: 7px 14px; border-radius: 99px; background: #e3efe8; color: #1d6b4f; }}
.r {{ background: #1d6b4f; color: #fff; display: flex; flex-direction: column; justify-content: center; gap: 30px; padding: 0 64px; }}
.stat b {{ display: block; font-size: 76px; font-weight: 750; letter-spacing: -0.04em; line-height: 1; }}
.stat span {{ font-size: 20px; color: #cfe7dc; }}
</style></head><body>
<div class="l">
  <div class="brand">{logo}Watt Forge</div>
  <h1>Converter design from first principles</h1>
  <p>Lessons, live loss models, eight MPPT algorithms benchmarked on EN 50530-style tests, and a hybrid GaN buck-boost reference design for solar.</p>
  <div class="chips"><span class="chip">Web + desktop app</span><span class="chip">Python &middot; JS &middot; C parity</span><span class="chip">Best MPPT {100 * best:.2f} %</span><span class="chip">MIT</span></div>
</div>
<div class="r">
  <div class="stat"><b>99.45 %</b><span>flagship predicted peak efficiency (56 V to 48 V, 400 W)</span></div>
  <div class="stat"><b>8</b><span>MPPT algorithms, benchmarked the EN 50530 way</span></div>
  <div class="stat"><b>3</b><span>languages, one tested implementation</span></div>
</div>
</body></html>"""


async def main():
    from playwright.async_api import async_playwright
    tmp = ROOT / "build" / "social.html"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(html())
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 640})
        await pg.goto(tmp.as_uri())
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(DOCS / "img" / "social-preview.png"))
        await b.close()
    print("wrote docs/img/social-preview.png")


if __name__ == "__main__":
    asyncio.run(main())
