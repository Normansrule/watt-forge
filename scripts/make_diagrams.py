"""Animated schematic SVGs (README + site), the annotated flagship schematic, and the
control state-machine diagram. Pure SVG + CSS keyframes, so they animate inside a
GitHub README <img> and need no script (the site's strict CSP allows them too).

    python scripts/make_diagrams.py
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
PERIOD_S = 2.4  # animation seconds per switching period

STYLE = """
<style>
  .bg{fill:#fcfcfb} .w{stroke:#52514e;stroke-width:2;fill:none;stroke-linejoin:round;stroke-linecap:round}
  .c{stroke:#0b0b0b;stroke-width:2.2;fill:none;stroke-linecap:round} .fill{fill:#0b0b0b}
  .t{font:600 13px system-ui,-apple-system,Segoe UI,sans-serif;fill:#0b0b0b}
  .s{font:12px system-ui,-apple-system,Segoe UI,sans-serif;fill:#52514e}
  .m{font:11px system-ui,-apple-system,Segoe UI,sans-serif;fill:#8a8984}
  .ax{stroke:#d8d7d2;stroke-width:1}
  .p1{stroke:#2a78d6} .p2{stroke:#eb6834} .p3{stroke:#1baf7a} .p4{stroke:#e87ba4}
  .cur{stroke-width:7;fill:none;stroke-linecap:round;stroke-linejoin:round;opacity:0;stroke-dasharray:4 14}
  @keyframes flow{to{stroke-dashoffset:-18}}
  .wave{stroke-width:2;fill:none} .v{stroke:#2a78d6} .i{stroke:#eb6834}
  .cursor{stroke:#0b0b0b;stroke-width:1.2;opacity:.55}
  .box{fill:#f2f1ed;stroke:#d8d7d2} .hi{fill:#e5efff;stroke:#2a78d6}
  @media (prefers-color-scheme: dark){
    .bg{fill:#1a1a19} .w{stroke:#c3c2b7} .c{stroke:#ffffff} .fill{fill:#ffffff}
    .t{fill:#ffffff} .s{fill:#c3c2b7} .m{fill:#8f8e87} .ax{stroke:#3a3a37}
    .p1{stroke:#3987e5} .p2{stroke:#d95926} .p3{stroke:#199e70} .p4{stroke:#d55181}
    .v{stroke:#3987e5} .i{stroke:#d95926} .cursor{stroke:#ffffff}
    .box{fill:#262624;stroke:#3a3a37} .hi{fill:#1f2d44;stroke:#3987e5}
  }
</style>
"""


class Svg:
    def __init__(self, w: int, h: int, title: str):
        self.w, self.h = w, h
        self.parts: List[str] = []
        self.css: List[str] = []
        self.kf = 0
        self.title = title

    def add(self, s: str):
        self.parts.append(s)

    # -------------------------------------------------------------- animation
    def window_anim(self, intervals: Sequence[Tuple[float, float]], on_val: float = 1.0) -> str:
        """Return a class name whose opacity is on_val inside the intervals (fractions of a period)."""
        pts = []
        for s, e in intervals:
            pts.append((s, on_val))
            pts.append((e, 0.0))
        pts.sort()

        def val(x):
            v = 0.0
            for s, e in intervals:
                if s <= x < e:
                    v = on_val
            return v
        stops = sorted({0.0, 1.0, *[p[0] for p in pts]})
        name = f"k{self.kf}"
        self.kf += 1
        frames = []
        for x in stops:
            frames.append(f"{100*x:.3f}%{{opacity:{val(min(x, 0.99999)):g}}}")
        self.css.append(f"@keyframes {name}{{{' '.join(frames)}}}")
        self.css.append(f".{name}{{animation:{name} {PERIOD_S}s steps(1,end) infinite}}")
        self.css.append(f".{name}c{{animation:flow 0.6s linear infinite,{name} {PERIOD_S}s steps(1,end) infinite}}")
        return name

    def render(self) -> str:
        extra = "<style>" + "\n".join(self.css) + "</style>" if self.css else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
                f'role="img" aria-label="{self.title}"><title>{self.title}</title>{STYLE}{extra}'
                f'<rect class="bg" width="{self.w}" height="{self.h}" rx="10"/>' + "".join(self.parts) + "</svg>")

    # -------------------------------------------------------------- primitives
    def wire(self, pts):
        self.add('<polyline class="w" points="' + " ".join(f"{x},{y}" for x, y in pts) + '"/>')

    def dot(self, x, y):
        self.add(f'<circle class="fill" cx="{x}" cy="{y}" r="3.2"/>')

    def text(self, x, y, s, cls="s", anchor="start"):
        s = re.sub(r"&(?!#)", "&amp;", s)
        s = re.sub(r"<(?![/]?tspan)", "&lt;", s)
        self.add(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{s}</text>')

    def source(self, x, y1, y2, label="V<tspan dy=\"4\" font-size=\"9\">in</tspan>"):
        ym = (y1 + y2) / 2
        self.wire([(x, y1), (x, ym - 18)])
        self.wire([(x, ym + 18), (x, y2)])
        self.add(f'<circle class="c" cx="{x}" cy="{ym}" r="18"/>')
        self.text(x, ym - 4, "+", "s", "middle")
        self.text(x, ym + 12, "&#8722;", "s", "middle")
        self.text(x - 30, ym + 4, label, "t", "end")

    def cap(self, x, y1, y2, label="", horizontal=False):
        if horizontal:
            xm = (x + y1) / 2  # here x=x1, y1=x2, y2=y
            x1, x2, y = x, y1, y2
            xm = (x1 + x2) / 2
            self.wire([(x1, y), (xm - 4, y)])
            self.wire([(xm + 4, y), (x2, y)])
            self.add(f'<line class="c" x1="{xm-4}" y1="{y-13}" x2="{xm-4}" y2="{y+13}"/>')
            self.add(f'<line class="c" x1="{xm+4}" y1="{y-13}" x2="{xm+4}" y2="{y+13}"/>')
            if label:
                self.text(xm, y - 18, label, "s", "middle")
            return
        ym = (y1 + y2) / 2
        self.wire([(x, y1), (x, ym - 4)])
        self.wire([(x, ym + 4), (x, y2)])
        self.add(f'<line class="c" x1="{x-13}" y1="{ym-4}" x2="{x+13}" y2="{ym-4}"/>')
        self.add(f'<line class="c" x1="{x-13}" y1="{ym+4}" x2="{x+13}" y2="{ym+4}"/>')
        if label:
            self.text(x + 18, ym + 4, label)

    def load(self, x, y1, y2, label="Load"):
        ym = (y1 + y2) / 2
        self.wire([(x, y1), (x, ym - 24)])
        pts = [(x, ym - 24)]
        for k in range(6):
            pts.append((x + (9 if k % 2 == 0 else -9), ym - 20 + k * 8))
        pts.append((x, ym + 24))
        self.add('<polyline class="c" points="' + " ".join(f"{a},{b}" for a, b in pts) + '"/>')
        self.wire([(x, ym + 24), (x, y2)])
        self.text(x + 16, ym + 4, label)

    def inductor(self, x1, y1, x2, y2, label="L"):
        horiz = y1 == y2
        n = 4
        if horiz:
            L = x2 - x1
            pad = L * 0.15
            a, b = x1 + pad, x2 - pad
            self.wire([(x1, y1), (a, y1)])
            self.wire([(b, y1), (x2, y1)])
            r = (b - a) / (2 * n)
            d = f"M{a},{y1}" + "".join(f" a{r},{r} 0 0 1 {2*r},0" for _ in range(n))
            self.add(f'<path class="c" d="{d}"/>')
            self.text((x1 + x2) / 2, y1 - r - 8, label, "s", "middle")
        else:
            L = y2 - y1
            pad = L * 0.15
            a, b = y1 + pad, y2 - pad
            self.wire([(x1, y1), (x1, a)])
            self.wire([(x1, b), (x1, y2)])
            r = (b - a) / (2 * n)
            d = f"M{x1},{a}" + "".join(f" a{r},{r} 0 0 1 0,{2*r}" for _ in range(n))
            self.add(f'<path class="c" d="{d}"/>')
            self.text(x1 + r + 8, (y1 + y2) / 2 + 4, label)

    def switch(self, x1, y1, x2, y2, label, on_intervals, lab_dx=0, lab_dy=0):
        """A switch drawn open/closed, toggled by the animation."""
        horiz = y1 == y2
        if horiz:
            L = x2 - x1
            a, b = x1 + L * 0.3, x2 - L * 0.3
            self.wire([(x1, y1), (a, y1)])
            self.wire([(b, y1), (x2, y1)])
            closed = f'<line class="c" x1="{a}" y1="{y1}" x2="{b}" y2="{y1}"/>'
            opened = f'<line class="c" x1="{a}" y1="{y1}" x2="{b-3}" y2="{y1-16}"/>'
            tx, ty = (x1 + x2) / 2 + lab_dx, y1 - 22 + lab_dy
            self.add(f'<circle class="fill" cx="{a}" cy="{y1}" r="2.6"/><circle class="fill" cx="{b}" cy="{y1}" r="2.6"/>')
        else:
            L = y2 - y1
            a, b = y1 + L * 0.3, y2 - L * 0.3
            self.wire([(x1, y1), (x1, a)])
            self.wire([(x1, b), (x1, y2)])
            closed = f'<line class="c" x1="{x1}" y1="{a}" x2="{x1}" y2="{b}"/>'
            opened = f'<line class="c" x1="{x1}" y1="{a}" x2="{x1+16}" y2="{b-3}"/>'
            tx, ty = x1 + 20 + lab_dx, (y1 + y2) / 2 + 4 + lab_dy
            self.add(f'<circle class="fill" cx="{x1}" cy="{a}" r="2.6"/><circle class="fill" cx="{x1}" cy="{b}" r="2.6"/>')
        k_on = self.window_anim(on_intervals)
        off_iv = _complement(on_intervals)
        k_off = self.window_anim(off_iv)
        self.add(f'<g class="on {k_on}">{closed}</g><g class="off {k_off}">{opened}</g>')
        self.text(tx, ty, label, "s", "start" if not horiz else "middle")

    def diode(self, x1, y1, x2, y2, label=""):
        """Horizontal diode pointing right (x1 -> x2) or vertical pointing up (y1 bottom -> y2 top)."""
        if y1 == y2:
            xm = (x1 + x2) / 2
            self.wire([(x1, y1), (xm - 9, y1)])
            self.wire([(xm + 9, y1), (x2, y1)])
            self.add(f'<polygon class="c" points="{xm-9},{y1-10} {xm-9},{y1+10} {xm+9},{y1}"/>')
            self.add(f'<line class="c" x1="{xm+9}" y1="{y1-10}" x2="{xm+9}" y2="{y1+10}"/>')
            self.text(xm, y1 - 16, label, "s", "middle")

    def ground(self, x, y):
        self.add(f'<line class="c" x1="{x-12}" y1="{y}" x2="{x+12}" y2="{y}"/><line class="c" x1="{x-7}" y1="{y+5}" x2="{x+7}" y2="{y+5}"/>'
                 f'<line class="c" x1="{x-3}" y1="{y+10}" x2="{x+3}" y2="{y+10}"/>')

    def current(self, pts, cls, intervals):
        k = self.window_anim(intervals)
        self.add(f'<polyline class="cur {cls} {k}c" points="' + " ".join(f"{x},{y}" for x, y in pts) + '"/>')

    def waveforms(self, x0, y0, w, h, v_levels_fn, i_fn, v_label, i_label, periods=2):
        """Two stacked traces over `periods` periods with an animated cursor."""
        hh = h / 2 - 8
        for k, (fn, cls, lab) in enumerate(((v_levels_fn, "v", v_label), (i_fn, "i", i_label))):
            yb = y0 + k * (hh + 16)
            self.add(f'<line class="ax" x1="{x0}" y1="{yb+hh}" x2="{x0+w}" y2="{yb+hh}"/>')
            self.add(f'<line class="ax" x1="{x0}" y1="{yb}" x2="{x0}" y2="{yb+hh}"/>')
            pts = []
            n = 400
            vals = [fn((j / n * periods) % 1.0) for j in range(n + 1)]
            lo, hi = min(vals), max(vals)
            if hi - lo < 1e-9:
                lo, hi = lo - 1, hi + 1
            for j, v in enumerate(vals):
                x = x0 + w * j / n
                y = yb + hh - (v - lo) / (hi - lo) * (hh - 6) - 3
                pts.append((round(x, 1), round(y, 1)))
            self.add(f'<polyline class="wave {cls}" points="' + " ".join(f"{a},{b}" for a, b in pts) + '"/>')
            self.text(x0 - 8, yb + hh / 2 + 4, lab, "s", "end")
        self.css.append(f"@keyframes cur{{from{{transform:translateX(0)}}to{{transform:translateX({w}px)}}}}")
        self.css.append(f".cursor{{animation:cur {PERIOD_S*periods}s linear infinite}}")
        self.add(f'<line class="cursor" x1="{x0}" y1="{y0-4}" x2="{x0}" y2="{y0+h}"/>')


def _complement(iv):
    iv = sorted(iv)
    out, t = [], 0.0
    for s, e in iv:
        if s > t:
            out.append((t, s))
        t = max(t, e)
    if t < 1.0:
        out.append((t, 1.0))
    return out


def _tri(d, lo=0.0, hi=1.0):
    """Inductor current shape for a two-level converter with duty d (rises during d)."""
    def f(x):
        if x < d:
            return lo + (hi - lo) * x / d
        return hi - (hi - lo) * (x - d) / (1 - d)
    return f


def _sq(d, hi=1.0, lo=0.0):
    return lambda x: hi if x < d else lo


def buck(d=0.4):
    s = Svg(720, 430, "Synchronous buck converter, animated")
    s.text(20, 26, "Synchronous buck  -  Vout = D Vin", "t")
    s.text(20, 44, f"D = {d}: blue path while S1 is on, orange while S2 is on (dashes show current flow)", "m")
    top, gnd = 90, 220
    s.source(70, top, gnd)
    s.wire([(70, top), (150, top)])
    s.switch(150, top, 250, top, "S1", [(0, d)])
    s.wire([(250, top), (290, top)])
    s.dot(290, top)
    s.switch(290, top, 290, gnd, "S2", [(d, 1)])
    s.inductor(290, top, 470, top)
    s.wire([(470, top), (560, top), (660, top)])
    s.dot(560, top)
    s.cap(560, top, gnd, "C")
    s.load(660, top, gnd)
    s.wire([(70, gnd), (660, gnd)])
    s.ground(380, gnd)
    s.text(600, top - 12, "V<tspan dy=\"4\" font-size=\"9\">out</tspan>", "t")
    s.current([(70, gnd - 60), (70, top), (290, top), (470, top), (660, top), (660, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(290, gnd), (290, top), (470, top), (660, top), (660, gnd), (290, gnd)], "p2", [(d, 1)])
    s.waveforms(90, 270, 600, 140, _sq(d), _tri(d), "v_sw", "i_L")
    return s.render()


def boost(d=0.5):
    s = Svg(720, 430, "Synchronous boost converter, animated")
    s.text(20, 26, "Synchronous boost  -  Vout = Vin / (1 - D)", "t")
    s.text(20, 44, f"D = {d}: blue = S1 on (inductor charges from Vin), orange = S2 on (inductor + Vin feed the output)", "m")
    top, gnd = 90, 220
    s.source(70, top, gnd)
    s.wire([(70, top), (110, top)])
    s.inductor(110, top, 290, top)
    s.dot(310, top)
    s.wire([(290, top), (330, top)])
    s.switch(310, top, 310, gnd, "S1", [(0, d)])
    s.switch(330, top, 450, top, "S2", [(d, 1)])
    s.wire([(450, top), (660, top)])
    s.dot(560, top)
    s.cap(560, top, gnd, "C")
    s.load(660, top, gnd)
    s.wire([(70, gnd), (660, gnd)])
    s.ground(430, gnd)
    s.text(600, top - 12, "V<tspan dy=\"4\" font-size=\"9\">out</tspan>", "t")
    s.current([(70, gnd - 60), (70, top), (310, top), (310, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(70, gnd - 60), (70, top), (450, top), (660, top), (660, gnd), (70, gnd), (70, gnd - 60)], "p2", [(d, 1)])
    s.waveforms(90, 270, 600, 140, _sq(d), _tri(d), "v_sw", "i_L")
    return s.render()


def buck_boost(d=0.4):
    s = Svg(720, 430, "Inverting buck-boost converter, animated")
    s.text(20, 26, "Inverting buck-boost  -  Vout = -D Vin / (1 - D)", "t")
    s.text(20, 44, f"D = {d}: blue = S1 on (L charges from Vin), orange = S2 on (L dumps into the output, which goes negative)", "m")
    top, gnd = 90, 220
    s.source(70, top, gnd)
    s.wire([(70, top), (150, top)])
    s.switch(150, top, 260, top, "S1", [(0, d)])
    s.wire([(260, top), (300, top)])
    s.dot(300, top)
    s.inductor(300, top, 300, gnd, "L")
    s.switch(300, top, 440, top, "S2", [(d, 1)])
    s.wire([(440, top), (660, top)])
    s.dot(560, top)
    s.cap(560, top, gnd, "C")
    s.load(660, top, gnd)
    s.wire([(70, gnd), (660, gnd)])
    s.ground(430, gnd)
    s.text(594, top - 12, "&#8722;V<tspan dy=\"4\" font-size=\"9\">out</tspan>", "t")
    s.current([(70, gnd - 60), (70, top), (300, top), (300, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(660, top), (300, top), (300, gnd), (660, gnd), (660, top)], "p2", [(d, 1)])
    s.waveforms(90, 270, 600, 140, lambda x: 1.0 if x < d else -0.8, _tri(d), "v_L", "i_L")
    return s.render()


def four_switch(d=0.5):
    s = Svg(720, 430, "Four-switch non-inverting buck-boost, animated")
    s.text(20, 26, "Four-switch buck-boost (buck-boost mode)  -  Vout = Vin D / (1 - D)", "t")
    s.text(20, 44, "blue = S1 + S3 on (L charges), orange = S2 + S4 on (L feeds the output); in buck or boost mode one leg stops switching", "m")
    top, gnd = 90, 220
    s.source(70, top, gnd)
    s.wire([(70, top), (110, top)])
    s.switch(110, top, 200, top, "S1", [(0, d)])
    s.wire([(200, top), (230, top)])
    s.dot(230, top)
    s.switch(230, top, 230, gnd, "S2", [(d, 1)])
    s.inductor(230, top, 400, top)
    s.dot(400, top)
    s.switch(400, top, 400, gnd, "S3", [(0, d)])
    s.switch(400, top, 500, top, "S4", [(d, 1)])
    s.wire([(500, top), (660, top)])
    s.dot(570, top)
    s.cap(570, top, gnd, "C")
    s.load(660, top, gnd)
    s.wire([(70, gnd), (660, gnd)])
    s.ground(320, gnd)
    s.current([(70, gnd - 60), (70, top), (400, top), (400, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(230, gnd), (230, top), (660, top), (660, gnd), (230, gnd)], "p2", [(d, 1)])
    s.waveforms(90, 270, 600, 140, lambda x: 1.0 if x < d else -1.0, _tri(d), "v_L", "i_L")
    return s.render()


def sepic(d=0.5):
    s = Svg(720, 430, "SEPIC converter, animated")
    s.text(20, 26, "SEPIC  -  Vout = Vin D / (1 - D), non-inverting, input current is continuous", "t")
    s.text(20, 44, "blue = S1 on (L1 charges from Vin, C1 charges L2), orange = S2 on (both inductors feed the output)", "m")
    top, gnd = 90, 220
    s.source(70, top, gnd)
    s.wire([(70, top), (100, top)])
    s.inductor(100, top, 220, top, "L1")
    s.dot(240, top)
    s.wire([(220, top), (260, top)])
    s.switch(240, top, 240, gnd, "S1", [(0, d)])
    s.cap(260, 330, top, horizontal=True, label="C1")
    s.dot(350, top)
    s.wire([(330, top), (370, top)])
    s.inductor(350, top, 350, gnd, "L2")
    s.switch(370, top, 470, top, "S2", [(d, 1)])
    s.wire([(470, top), (660, top)])
    s.dot(570, top)
    s.cap(570, top, gnd, "C")
    s.load(660, top, gnd)
    s.wire([(70, gnd), (660, gnd)])
    s.ground(430, gnd)
    s.current([(70, gnd - 60), (70, top), (240, top), (240, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(350, top + 30), (350, top), (240, top), (240, gnd), (350, gnd), (350, top + 30)], "p3", [(0, d)])
    s.current([(70, gnd - 60), (70, top), (470, top), (660, top), (660, gnd), (70, gnd), (70, gnd - 60)], "p2", [(d, 1)])
    s.current([(350, gnd), (350, top), (660, top)], "p4", [(d, 1)])
    s.waveforms(90, 270, 600, 140, _sq(d), _tri(d), "v_S1", "i_L1")
    return s.render()


def cuk(d=0.5):
    s = Svg(720, 430, "Cuk converter, animated")
    s.text(20, 26, "Cuk  -  Vout = -Vin D / (1 - D); energy moves through C1, both terminal currents are smooth", "t")
    s.text(20, 44, "blue/aqua = S1 on (L1 charges; C1 drives L2 and the load), orange/pink = S2 on (L1 recharges C1)", "m")
    top, gnd = 90, 220
    s.source(70, top, gnd)
    s.wire([(70, top), (100, top)])
    s.inductor(100, top, 220, top, "L1")
    s.dot(240, top)
    s.wire([(220, top), (260, top)])
    s.switch(240, top, 240, gnd, "S1", [(0, d)])
    s.cap(260, 330, top, horizontal=True, label="C1")
    s.dot(350, top)
    s.wire([(330, top), (370, top)])
    s.switch(350, top, 350, gnd, "S2", [(d, 1)])
    s.inductor(370, top, 500, top, "L2")
    s.wire([(500, top), (660, top)])
    s.dot(570, top)
    s.cap(570, top, gnd, "C")
    s.load(660, top, gnd)
    s.wire([(70, gnd), (660, gnd)])
    s.ground(430, gnd)
    s.text(594, top - 12, "&#8722;V<tspan dy=\"4\" font-size=\"9\">out</tspan>", "t")
    s.current([(70, gnd - 60), (70, top), (240, top), (240, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(660, gnd), (660, top), (350, top), (240, top), (240, gnd), (660, gnd)], "p3", [(0, d)])
    s.current([(70, gnd - 60), (70, top), (350, top), (350, gnd), (70, gnd), (70, gnd - 60)], "p2", [(d, 1)])
    s.current([(350, gnd), (350, top), (660, top), (660, gnd), (350, gnd)], "p4", [(d, 1)])
    s.waveforms(90, 270, 600, 140, _sq(d), _tri(d), "v_S1", "i_L1")
    return s.render()


def flyback(d=0.4):
    s = Svg(720, 430, "Flyback converter, animated")
    s.text(20, 26, "Flyback  -  Vout = n Vin D / (1 - D); a coupled inductor stores energy and gives isolation", "t")
    s.text(20, 44, "blue = S1 on (primary magnetizing current rises), orange = S2 on (energy leaves through the secondary)", "m")
    top, gnd = 80, 225
    s.source(70, top, gnd)
    s.wire([(70, top), (220, top)])
    s.inductor(220, top, 220, 160, "Np")
    s.switch(220, 160, 220, gnd, "S1", [(0, d)])
    s.add('<line class="c" x1="258" y1="85" x2="258" y2="160"/><line class="c" x1="266" y1="85" x2="266" y2="160"/>')
    s.add('<circle class="fill" cx="240" cy="92" r="3"/><circle class="fill" cx="292" cy="152" r="3"/>')
    s.inductor(300, top, 300, 160, "Ns")
    s.wire([(300, 160), (300, 200), (660, 200)])
    s.switch(300, top, 440, top, "S2", [(d, 1)])
    s.wire([(440, top), (660, top)])
    s.dot(570, top)
    s.cap(570, top, 200, "C")
    s.load(660, top, 200)
    s.wire([(70, gnd), (220, gnd)])
    s.ground(145, gnd)
    s.ground(480, 200)
    s.text(330, 245, "primary and secondary grounds are isolated", "m")
    s.current([(70, gnd - 60), (70, top), (220, top), (220, gnd), (70, gnd), (70, gnd - 60)], "p1", [(0, d)])
    s.current([(300, 160), (300, top), (660, top), (660, 200), (300, 200), (300, 160)], "p2", [(d, 1)])
    s.waveforms(90, 275, 600, 140, _sq(d), lambda x: (x / d) if x < d else 0.0, "v_S1", "i_pri")
    return s.render()


def flagship(d=0.75):
    """Three-level input leg in buck mode (output leg static)."""
    s = Svg(760, 470, "Flagship hybrid three-level buck-boost, input leg switching, animated")
    s.text(20, 26, "Flagship: three-level flying-capacitor leg (buck mode shown, output leg static)", "t")
    s.text(20, 44, "Q1 and Q2 are 180 degrees apart. Node A steps between Vin/2 and Vin at twice the switching frequency.", "m")
    s.text(20, 60, "blue: Q1+Q2 (straight through)  aqua: Q1+Q3 (CF1 charges)  pink: Q4+Q2 (CF1 discharges)", "m")
    rail, gnd = 90, 300
    x = 230
    s.source(70, rail, gnd)
    s.wire([(70, rail), (x, rail)])
    q1 = [(0, d)]
    q2 = [(0.5, 1.0), (0.0, d - 0.5)] if d > 0.5 else [(0.5, 0.5 + d)]
    s.switch(x, rail, x, 140, "Q1", q1)
    s.dot(x, 140)
    s.switch(x, 140, x, 190, "Q2", q2)
    s.dot(x, 195)
    s.wire([(x, 190), (x, 200)])
    s.switch(x, 200, x, 245, "Q3", _complement(q2))
    s.dot(x, 250)
    s.wire([(x, 245), (x, 250)])
    s.switch(x, 250, x, gnd, "Q4", _complement(q1))
    s.wire([(x, 140), (150, 140)])
    s.cap(150, 140, 250, "")
    s.text(108, 199, "CF1", "s")
    s.wire([(150, 250), (x, 250)])
    s.text(x + 34, 200, "A", "t")
    s.inductor(x, 195, 470, 195, "L")
    xo = 470
    s.dot(xo, 195)
    s.wire([(xo, 195), (xo, 140)])
    s.text(xo + 20, 170, "Q6, Q5 on (static)", "m")
    s.wire([(xo, 140), (xo, rail), (690, rail)])
    s.dot(600, rail)
    s.cap(600, rail, gnd, "C")
    s.load(690, rail, gnd)
    s.wire([(70, gnd), (690, gnd)])
    s.ground(380, gnd)
    s.text(630, rail - 12, "V<tspan dy=\"4\" font-size=\"9\">out</tspan>", "t")
    both = [(0, d - 0.5), (0.5, d)] if d > 0.5 else []
    s.current([(70, 240), (70, rail), (x, rail), (x, 195), (xo, 195), (xo, rail), (690, rail), (690, gnd), (70, gnd), (70, 240)], "p1", both)
    s.current([(70, 240), (70, rail), (x, rail), (x, 140), (150, 140), (150, 250), (x, 250), (x, 195), (xo, 195), (xo, rail), (690, rail), (690, gnd), (70, gnd), (70, 240)], "p3",
              [(d - 0.5, 0.5)] if d > 0.5 else [(0, d)])
    s.current([(x, gnd), (x, 250), (150, 250), (150, 140), (x, 140), (x, 195), (xo, 195), (xo, rail), (690, rail), (690, gnd), (x, gnd)], "p4",
              [(d, 1.0)] if d > 0.5 else [(0.5, 0.5 + d)])

    def va(t):
        a = 1 if t < d else 0
        b = 1 if (t >= 0.5 and t < 0.5 + d) or (t < d - 0.5) else 0
        return (a + b) / 2

    def il(t):
        # ripple at 2 fs, zero-mean shape
        tt = (2 * t) % 1.0
        dd = 2 * d - 1 if d > 0.5 else 2 * d
        return (tt / dd) if tt < dd else 1 - (tt - dd) / (1 - dd)
    s.waveforms(100, 330, 620, 130, va, il, "v_A", "i_L")
    return s.render()


# ------------------------------------------------------------------ static diagrams

def flagship_schematic() -> str:
    """Annotated power-stage schematic of the reference design (static)."""
    s = Svg(980, 600, "Flagship reference design: annotated power stage schematic")
    s.text(20, 28, "Watt Forge flagship: hybrid three-level GaN buck-boost, 12-60 V panel -> 40-58 V battery, 400 W", "t")
    s.text(20, 46, "REFERENCE DESIGN - simulate and review before use. High voltage and stored energy: see SAFETY.md.", "m")
    rail, gnd = 120, 470
    s.source(60, rail + 40, gnd - 40, "PV")
    s.wire([(60, rail + 40), (60, rail), (90, rail)])
    s.wire([(60, gnd - 40), (60, gnd)])
    # input disconnect BDS
    s.add(f'<rect class="box" x="90" y="{rail-18}" width="70" height="36" rx="5"/>')
    s.text(125, rail + 5, "Q_IN", "s", "middle")
    s.text(125, rail - 26, "BDS INV100FQ030C", "m", "middle")
    s.wire([(160, rail), (190, rail)])
    s.add(f'<rect class="box" x="190" y="{rail-10}" width="36" height="20" rx="3"/>')
    s.text(208, rail + 28, "RS1 1 mOhm", "m", "middle")
    s.wire([(226, rail), (330, rail)])
    s.dot(250, rail)
    s.cap(250, rail, gnd, "")
    s.text(242, 290, "CIN", "t", "end")
    s.text(242, 306, "6x10 uF", "m", "end")
    s.text(242, 320, "+ 2x33 uF", "m", "end")
    # input leg
    x = 380
    s.wire([(330, rail), (x, rail)])
    for (y1, y2, lab) in ((rail, rail + 70, "Q1"), (rail + 80, rail + 150, "Q2"), (rail + 170, rail + 240, "Q3"), (rail + 250, gnd, "Q4")):
        s.add(f'<rect class="hi" x="{x-16}" y="{y1+14}" width="32" height="{y2-y1-28}" rx="4"/>')
        s.wire([(x, y1), (x, y1 + 14)])
        s.wire([(x, y2 - 14), (x, y2)])
        s.text(x - 24, (y1 + y2) / 2 + 4, lab, "t", "end")
    s.wire([(x, rail + 70), (x, rail + 80)])
    s.wire([(x, rail + 150), (x, rail + 170)])
    s.wire([(x, rail + 240), (x, rail + 250)])
    s.dot(x, rail + 75)
    s.dot(x, rail + 245)
    s.wire([(x, rail + 75), (325, rail + 75)])
    s.wire([(x, rail + 245), (325, rail + 245)])
    s.cap(325, rail + 75, rail + 245, "")
    s.text(318, rail + 145, "CF1", "t", "end")
    s.text(318, rail + 196, "4x10 uF", "m", "end")
    s.dot(x, rail + 160)
    s.text(x + 8, rail + 186, "A", "t")
    # inductor
    s.inductor(x, rail + 160, 620, rail + 160, "L1  SER2918H-472  4.7 uH")
    xo = 620
    s.dot(xo, rail + 160)
    # output leg
    for (y1, y2, lab) in ((rail, rail + 70, "Q5"), (rail + 80, rail + 150, "Q6"), (rail + 170, rail + 240, "Q7"), (rail + 250, gnd, "Q8")):
        s.add(f'<rect class="hi" x="{xo-16}" y="{y1+14}" width="32" height="{y2-y1-28}" rx="4"/>')
        s.wire([(xo, y1), (xo, y1 + 14)])
        s.wire([(xo, y2 - 14), (xo, y2)])
        s.text(xo + 24, (y1 + y2) / 2 + 4, lab, "t")
    s.wire([(xo, rail + 70), (xo, rail + 80)])
    s.wire([(xo, rail + 150), (xo, rail + 170)])
    s.wire([(xo, rail + 240), (xo, rail + 250)])
    s.dot(xo, rail + 75)
    s.dot(xo, rail + 245)
    s.wire([(xo, rail + 75), (675, rail + 75)])
    s.wire([(xo, rail + 245), (675, rail + 245)])
    s.cap(675, rail + 75, rail + 245, "")
    s.text(683, rail + 145, "CF2", "t")
    s.text(683, rail + 196, "4x10 uF", "m")
    s.text(xo - 8, rail + 186, "B", "t", "end")
    s.wire([(xo, rail), (760, rail)])
    s.dot(740, rail)
    s.cap(740, rail, gnd, "")
    s.text(752, 290, "COUT", "t")
    s.add(f'<rect class="box" x="760" y="{rail-10}" width="36" height="20" rx="3"/>')
    s.text(778, rail + 28, "RS2 1 mOhm", "m", "middle")
    s.wire([(796, rail), (880, rail), (880, rail + 40)])
    s.add(f'<rect class="c" x="862" y="{rail+40}" width="36" height="70" rx="4"/>')
    s.text(880, rail + 80, "BATT", "s", "middle")
    s.text(880, rail + 128, "48 V", "m", "middle")
    s.wire([(880, rail + 110), (880, gnd)])
    s.wire([(60, gnd), (880, gnd)])
    s.ground(500, gnd)
    # bypass BDS
    s.wire([(300, rail), (300, 80), (560, 80)])
    s.add('<rect class="box" x="560" y="62" width="80" height="36" rx="5"/>')
    s.text(600, 85, "Q_BP", "s", "middle")
    s.text(600, 56, "bypass BDS INV100FQ030C", "m", "middle")
    s.wire([(640, 80), (740, 80), (740, rail)])
    s.dot(300, rail)
    # annotations
    notes = [
        "Q1-Q8: EPC2361 100 V GaN, 1.0 mOhm max. Each blocks Vbus/2 in steady state (<= 30 V), full Vbus (60 V) during precharge.",
        "Flying caps self-balance at Vin/2 and Vout/2 with 180-degree phase-shifted PWM; node A/B step at 2x the switching frequency.",
        "Buck mode: output leg static (Q5,Q6 on). Boost mode: input leg static (Q1,Q2 on). Near Vout = 2 Vin the output leg is a soft-charged 1:2 SC stage.",
        "Bypass: when the panel's maximum power point sits within 2 % of the battery, Q_BP ties them together and all eight switches stop.",
        "Gate drive: ADuM4121 isolated drivers for the six floating switches, LMG1020 for Q4/Q8; controller STM32G474 (HRTIM, 184 ps).",
    ]
    for k, n in enumerate(notes):
        s.text(20, 510 + 17 * k, n, "m")
    return s.render()


def state_machine() -> str:
    s = Svg(944, 400, "Flagship controller state machine")
    s.text(20, 28, "Controller state machine (1 kHz supervisory tick; the reference C and Python are proven identical)", "t")
    boxes = {
        "INIT": (12, 150, "wait: Vin > 13 V for 1 s", "record Voc"),
        "PRECHARGE": (196, 150, "flying caps to Vbus/2", "50 ms"),
        "SWEEP": (380, 150, "40-step global scan", "0.95 Voc ... 0.45 Voc"),
        "TRACK": (580, 150, "P&O MPPT, adaptive step", "mode select + CV limit"),
        "BYPASS": (772, 150, "MPP within 2 % of Vbat", "switching stops"),
        "FAULT": (380, 280, "OVP, battery out of range,", "OCP, OTP: latched"),
    }
    for name, (x, y, a, b) in boxes.items():
        s.add(f'<rect class="{"hi" if name in ("TRACK", "BYPASS") else "box"}" x="{x}" y="{y}" width="156" height="64" rx="10"/>')
        s.text(x + 78, y + 22, name, "t", "middle")
        s.text(x + 78, y + 40, a, "m", "middle")
        s.text(x + 78, y + 54, b, "m", "middle")

    def arrow(x1, y1, x2, y2, label="", dy=-8):
        s.add(f'<line class="w" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-end="url(#ah)"/>')
        if label:
            s.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label, "m", "middle")
    s.add('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
          '<path d="M0,0 L10,5 L0,10 z" class="fill"/></marker></defs>')
    arrow(168, 182, 194, 182)
    arrow(352, 182, 378, 182)
    arrow(536, 182, 578, 182, "best", -10)
    arrow(736, 170, 770, 170, "in band", -8)
    arrow(770, 198, 738, 198, "every 2 s", 18)
    s.add('<path class="w" d="M658,150 C658,95 458,95 458,148" marker-end="url(#ah)"/>')
    s.text(550, 88, "power drops 30 % or every 5 min: re-sweep (partial shading)", "m", "middle")
    s.add('<path class="w" d="M380,312 C230,330 90,300 90,216" marker-end="url(#ah)"/>')
    s.text(200, 340, "fault clear for 5 s", "m", "middle")
    s.text(556, 300, "any state -> FAULT on a fault", "m")
    s.text(556, 316, "any running state -> INIT if Vin < 11 V (night)", "m")
    s.text(20, 372, "Inside TRACK the mode is BUCK if Vout/Vref < 0.97, BOOST if > 1.03, BUCK-BOOST between (1 % hysteresis);", "m")
    s.text(20, 388, "the switching frequency comes from a lookup table generated by the loss model (data/fs_lut.json).", "m")
    return s.render()


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    files = {
        "anim_buck.svg": buck(),
        "anim_boost.svg": boost(),
        "anim_buck_boost.svg": buck_boost(),
        "anim_four_switch.svg": four_switch(),
        "anim_sepic.svg": sepic(),
        "anim_cuk.svg": cuk(),
        "anim_flyback.svg": flyback(),
        "anim_flagship.svg": flagship(),
        "flagship_schematic.svg": flagship_schematic(),
        "state_machine.svg": state_machine(),
    }
    for name, svg in files.items():
        (IMG / name).write_text(svg)
    print("wrote", ", ".join(files))


if __name__ == "__main__":
    main()
