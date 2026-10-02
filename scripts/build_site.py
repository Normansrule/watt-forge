"""Wrap the page fragments in site/ with the shared chrome and write docs/*.html.

Each fragment starts with a header comment:
    <!-- title: Page title | path: learn/fundamentals.html | nav: learn | script: pages/fundamentals.js | desc: ... -->

    python scripts/build_site.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site"
OUT = ROOT / "docs"

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'self'")

NAV = [("learn", "learn/fundamentals.html", "Learn"), ("tools", "tools/designer.html", "Tools"),
       ("flagship", "flagship.html", "Flagship design"), ("sources", "sources.html", "Sources")]

LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect x="1" y="1" width="30" height="30" rx="7" fill="#1d6b4f"/>'
        '<path d="M6 21 h5 v-10 h5 v10 h5 v-10 h5" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/></svg>')

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="referrer" content="no-referrer">
<title>{title} - Watt Forge</title>
<meta name="description" content="{desc}">
<link rel="icon" href="{base}img/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{base}css/site.css">
<link rel="manifest" href="{base}manifest.webmanifest">
<link rel="apple-touch-icon" href="{base}img/apple-touch-icon.png">
<meta name="theme-color" content="#1d6b4f">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar"><div class="inner">
<a class="brand" href="{base}index.html">{logo}Watt Forge</a>
<nav class="nav" aria-label="Main">{nav}</nav>
<button class="theme-btn" type="button">Dark theme</button>
</div></header>
<div class="safety" role="note"><div class="inner">Design and simulation reference only. Solar and battery hardware is dangerous: high voltage, stored energy, fire risk. Any physical build is at your own risk and needs proper lab safety practice. <a href="{base}safety.html">Read the safety note</a>.</div></div>
<main id="main">
{body}
</main>
<footer><div class="inner">Watt Forge: open-source converter design, MIT licensed. Runs entirely in your browser: no accounts, no analytics, designs stay in this browser's storage. Every efficiency figure on this site is cited with its test conditions on the <a href="{base}sources.html">Sources</a> page. Models are predictions, not measurements.</div></footer>
<script type="module" src="{base}js/ui/ui.js"></script>
{script}
</body>
</html>
"""


def build():
    count = 0
    for frag in sorted(SRC.glob("*.html")):
        text = frag.read_text()
        m = re.match(r"<!--(.*?)-->\s*", text, re.S)
        if not m:
            raise SystemExit(f"{frag}: missing header comment")
        meta = dict(part.strip().split(":", 1) for part in m.group(1).split("|"))
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        body = text[m.end():]
        path = meta["path"]
        depth = path.count("/")
        base = "../" * depth
        cur = ' aria-current="page"'
        nav = "".join(
            f'<a href="{base}{href}"{cur if meta.get("nav") == key else ""}>{label}</a>'
            for key, href, label in NAV)
        script = f'<script type="module" src="{base}js/{meta["script"]}"></script>' if meta.get("script") else ""
        body = body.replace("{base}", base)
        html = TEMPLATE.format(csp=CSP, title=meta["title"], desc=meta.get("desc", meta["title"]), base=base,
                               logo=LOGO, nav=nav, body=body.strip(), script=script)
        dst = OUT / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(html)
        count += 1
    (OUT / "img" / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">' + LOGO[LOGO.index(">") + 1:])
    (OUT / ".nojekyll").write_text("")
    write_pwa()
    print(f"built {count} pages")


MANIFEST = {
    "name": "Watt Forge: converter design from first principles",
    "short_name": "Watt Forge",
    "description": "Power-converter lessons, live loss models and a hybrid GaN buck-boost reference design. Works offline once installed.",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "background_color": "#f7f5ef",
    "theme_color": "#1d6b4f",
    "icons": [
        {"src": "img/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "img/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "img/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# Not precached: the README-only GIF and the Markdown documents (they live on GitHub, not in the app).
PRECACHE_SKIP = {".gif", ".md"}


def write_pwa():
    """manifest.webmanifest + sw.js. The service worker's cache name is a hash of every precached
    file, so each deploy that changes content installs a fresh cache and deletes the old one."""
    (OUT / "manifest.webmanifest").write_text(json.dumps(MANIFEST, indent=1) + "\n")
    files = sorted(f for f in OUT.rglob("*") if f.is_file() and f.suffix not in PRECACHE_SKIP
                   and f.name not in ("sw.js", ".nojekyll"))
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.relative_to(OUT).as_posix().encode())
        digest.update(f.read_bytes())
    urls = ["./"] + [f.relative_to(OUT).as_posix() for f in files]
    sw = SW_TEMPLATE.replace("__VERSION__", digest.hexdigest()[:16]).replace("__URLS__", json.dumps(urls, indent=0))
    (OUT / "sw.js").write_text(sw)


SW_TEMPLATE = """// sw.js -- AUTO-GENERATED by scripts/build_site.py. Offline support for the installable web app.
// Same-origin only: it never fetches or caches anything from another site.
const CACHE = 'watt-forge-__VERSION__';
const PRECACHE = __URLS__;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith('watt-forge-') && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Pages: network first (fresh content when online), cache when offline.
// Everything else: cache first, filled from the network on a miss.
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then((res) => {
      const copy = res.clone();
      if (res.ok) caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true }).then((r) => r || caches.match('index.html'))));
    return;
  }
  e.respondWith(caches.match(req, { ignoreSearch: true }).then((hit) => hit || fetch(req).then((res) => {
    const copy = res.clone();
    if (res.ok && res.type === 'basic') caches.open(CACHE).then((c) => c.put(req, copy));
    return res;
  })));
});
"""


if __name__ == "__main__":
    build()
