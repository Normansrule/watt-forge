"""Static-site security and integrity checks, plus the browser-model parity run."""
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.rglob("*.html"))
CSP_REQUIRED = ["default-src 'self'", "script-src 'self'", "object-src 'none'", "base-uri 'none'", "form-action 'none'"]


class Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.csp, self.inline_scripts, self.style_attrs, self.handlers, self.ext_scripts = [], None, 0, 0, 0, []
        self._in_script_without_src = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp = a.get("content")
        if "style" in a:
            self.style_attrs += 1
        if any(k.startswith("on") for k in a):
            self.handlers += 1
        if tag == "script":
            if "src" not in a:
                self._in_script_without_src = True
            elif re.match(r"^(https?:)?//", a["src"]):
                self.ext_scripts.append(a["src"])
        for k in ("href", "src"):
            if k in a and a[k]:
                self.refs.append(a[k])

    def handle_data(self, data):
        if self._in_script_without_src and data.strip():
            self.inline_scripts += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script_without_src = False


def test_pages_exist():
    names = {p.relative_to(DOCS).as_posix() for p in PAGES}
    for need in ("index.html", "flagship.html", "sources.html", "learn/losses.html", "tools/designer.html", "tools/losses.html",
                 "tools/validator.html", "tools/devices.html", "tools/mppt.html", "tools/spice.html"):
        assert need in names


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.relative_to(DOCS).as_posix())
def test_page_security_and_links(page):
    c = Collect()
    c.feed(page.read_text())
    assert c.csp, "every page carries a Content-Security-Policy"
    for rule in CSP_REQUIRED:
        assert rule in c.csp
    assert "unsafe-inline" not in c.csp and "unsafe-eval" not in c.csp
    assert c.inline_scripts == 0
    assert c.style_attrs == 0, "inline style attributes are blocked by the CSP"
    assert c.handlers == 0
    assert not c.ext_scripts
    for ref in c.refs:
        if re.match(r"^(https?:|mailto:|#)", ref):
            continue
        target = (page.parent / ref.split("#")[0]).resolve()
        assert target.exists(), f"broken link {ref} in {page}"


def test_js_never_evaluates_strings():
    for js in (DOCS / "js").rglob("*.js"):
        src = js.read_text()
        assert not re.search(r"\beval\s*\(|new\s+Function\s*\(|\.innerHTML\s*=|document\.write|setAttribute\(\s*['\"]style", src), js
        assert "http://" not in src.replace("http://www.w3.org/2000/svg", "")
    for js in (DOCS / "js").rglob("*.js"):
        assert "fetch(" not in js.read_text() or js.name == "never", "the site makes no network requests"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_model_parity():
    out = subprocess.run(["node", str(ROOT / "tests" / "js" / "parity.mjs")], capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-2000:]


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo not installed")
def test_rust_netlist_guard():
    out = subprocess.run(["cargo", "test", "--quiet", "--offline"], cwd=ROOT / "desktop" / "netlist-guard",
                         capture_output=True, text=True, timeout=900)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]


def test_installable_web_app():
    import json
    man = json.loads((DOCS / "manifest.webmanifest").read_text())
    assert man["display"] == "standalone" and man["start_url"]
    for icon in man["icons"]:
        assert (DOCS / icon["src"]).is_file()
    sw = (DOCS / "sw.js").read_text()
    assert "self.location.origin" in sw, "service worker must stay same-origin"
    pre = json.loads(sw.split("const PRECACHE = ", 1)[1].split(";\n", 1)[0])
    for url in pre:
        if url != "./":
            assert (DOCS / url).is_file(), url
    for page in PAGES:
        assert 'rel="manifest"' in page.read_text(), page
