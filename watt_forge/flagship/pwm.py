"""Modulation and ideal-waveform reconstruction for the three-level four-switch buck-boost.

Switch naming (see hardware/flagship/schematic.svg):
    Input (buck-side) leg, bus Vin:   Q1 outer-top, Q2 inner-top, Q3 inner-bottom, Q4 outer-bottom, flying cap CF1
    Output (boost-side) leg, bus Vout: Q5 outer-top, Q6 inner-top, Q7 inner-bottom, Q8 outer-bottom, flying cap CF2
    Inductor L from node A (between Q2 and Q3) to node B (between Q6 and Q7).

State bits per segment: a=Q1 on, b=Q2 on (Q4 = not a, Q3 = not b); c=Q5 on, d=Q6 on (Q8 = not c, Q7 = not d).
With balanced flying capacitors (V_CF = Vbus/2):
    vA = Vin  * (a + b) / 2         -> levels 0, Vin/2, Vin at twice the switching frequency
    vB = Vout * (c + d) / 2
Flying-capacitor currents:  CF1: +iL when (a,b)=(1,0), -iL when (0,1);  CF2: -iL when (c,d)=(1,0), +iL when (0,1).
Input current  iin  = iL * a      Output current  iout = iL * c

Carrier timing (phase-shifted PWM, 180 degrees between the two switch pairs of a leg):
    Q1 on  [0, D1 T)            Q2 on  [T/2, T/2 + D1 T)
    Q8 on  [phi T, (phi + D2) T)   Q7 on  [(phi + 1/2) T, (phi + 1/2 + D2) T)     (bottom switches of the output leg)
A leg that is not switching ("static") holds both top switches on.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

EPS = 1e-15


@dataclass
class Segment:
    t0: float
    dur: float
    a: int
    b: int
    c: int
    d: int


@dataclass
class Edge:
    t: float
    leg: str       # "in" (buck-side) or "out" (boost-side)
    pair: str      # "outer" or "inner"
    incoming: str  # "top" or "bottom": the switch that turns ON at this edge


def _mod(x: float, T: float) -> float:
    y = x % T
    return 0.0 if abs(y - T) < 1e-15 * T else y


def _on(t: float, start: float, dur: float, T: float) -> bool:
    """Is t inside the (wrapping) interval [start, start+dur) mod T."""
    if dur <= 0:
        return False
    if dur >= T:
        return True
    rel = (t - start) % T
    return rel < dur


def build(d1: float, d2: float, phase: float, T: float, in_active: bool, out_active: bool):
    """Return (segments, edges) for one period."""
    times = {0.0, T}
    edges: List[Edge] = []
    if in_active:
        for start, pair in ((0.0, "outer"), (T / 2, "inner")):
            t_on = _mod(start, T)
            t_off = _mod(start + d1 * T, T)
            times.update((t_on, t_off))
            edges.append(Edge(t_on, "in", pair, "top"))
            edges.append(Edge(t_off, "in", pair, "bottom"))
    if out_active:
        for start, pair in ((phase * T, "outer"), (phase * T + T / 2, "inner")):
            t_on = _mod(start, T)             # bottom switch turns on
            t_off = _mod(start + d2 * T, T)   # bottom off -> top on
            times.update((t_on, t_off))
            edges.append(Edge(t_on, "out", pair, "bottom"))
            edges.append(Edge(t_off, "out", pair, "top"))
    ts = sorted(times)
    # merge near-duplicates
    uniq = [ts[0]]
    for t in ts[1:]:
        if t - uniq[-1] > 1e-12 * T:
            uniq.append(t)
    uniq[-1] = T
    segs: List[Segment] = []
    for t0, t1 in zip(uniq, uniq[1:]):
        tm = 0.5 * (t0 + t1)
        a = 1 if (not in_active or _on(tm, 0.0, d1 * T, T)) else 0
        b = 1 if (not in_active or _on(tm, T / 2, d1 * T, T)) else 0
        c = 1 if (not out_active or not _on(tm, phase * T, d2 * T, T)) else 0
        d = 1 if (not out_active or not _on(tm, phase * T + T / 2, d2 * T, T)) else 0
        segs.append(Segment(t0, t1 - t0, a, b, c, d))
    edges.sort(key=lambda e: e.t)
    return segs, edges


@dataclass
class Waveform:
    T: float
    segs: List[Segment]
    edges: List[Edge]
    knots: List[float]       # ripple current at each segment boundary (len = len(segs)+1), zero-mean
    v_avg_drop: float        # mean(vA - vB): the resistive drop the duty must supply

    def ripple_pp(self) -> float:
        return max(self.knots) - min(self.knots)

    def at(self, t: float) -> float:
        """Ripple current at time t (0 <= t <= T)."""
        for k, s in enumerate(self.segs):
            if t <= s.t0 + s.dur + 1e-18:
                frac = 0.0 if s.dur <= 0 else (t - s.t0) / s.dur
                return self.knots[k] + (self.knots[k + 1] - self.knots[k]) * frac
        return self.knots[-1]


def ideal_ripple(vin: float, vout: float, l: float, segs: List[Segment], edges: List[Edge], T: float) -> Waveform:
    """Zero-mean inductor ripple from ideal (balanced) node voltages."""
    dv = [vin * (s.a + s.b) / 2.0 - vout * (s.c + s.d) / 2.0 for s in segs]
    vbar = sum(v * s.dur for v, s in zip(dv, segs)) / T
    knots = [0.0]
    for v, s in zip(dv, segs):
        knots.append(knots[-1] + (v - vbar) / l * s.dur)
    # mean of piecewise-linear
    area = sum(s.dur * (knots[k] + knots[k + 1]) / 2.0 for k, s in enumerate(segs))
    mean = area / T
    knots = [x - mean for x in knots]
    return Waveform(T, segs, edges, knots, vbar)


# ---------------------------------------------------------------- integrals

def avg_i(w: Waveform, il: float, mask=None) -> float:
    """<(IL + i~) * mask> over the period; mask(seg) -> 0/1."""
    acc = 0.0
    for k, s in enumerate(w.segs):
        if mask is not None and not mask(s):
            continue
        p, q = il + w.knots[k], il + w.knots[k + 1]
        acc += s.dur * (p + q) / 2.0
    return acc / w.T


def avg_i2(w: Waveform, il: float, mask=None) -> float:
    acc = 0.0
    for k, s in enumerate(w.segs):
        if mask is not None and not mask(s):
            continue
        p, q = il + w.knots[k], il + w.knots[k + 1]
        acc += s.dur * (p * p + p * q + q * q) / 3.0
    return acc / w.T


def frac(w: Waveform, mask) -> float:
    return sum(s.dur for s in w.segs if mask(s)) / w.T


def cf1_mask(s: Segment) -> int:
    return 1 if s.a != s.b else 0


def cf2_mask(s: Segment) -> int:
    return 1 if s.c != s.d else 0


def in_mask(s: Segment) -> int:
    return s.a


def out_mask(s: Segment) -> int:
    return s.c


def edge_current(w: Waveform, il: float, e: Edge) -> float:
    return il + w.at(e.t)


def cf_charge_pp(w: Waveform, il: float, which: int) -> float:
    """Peak-to-peak flying-capacitor charge swing over the period [C]."""
    q = 0.0
    lo = hi = 0.0
    for k, s in enumerate(w.segs):
        if which == 1:
            sign = (1 if (s.a, s.b) == (1, 0) else -1 if (s.a, s.b) == (0, 1) else 0)
        else:
            sign = (-1 if (s.c, s.d) == (1, 0) else 1 if (s.c, s.d) == (0, 1) else 0)
        p, r = il + w.knots[k], il + w.knots[k + 1]
        q += sign * s.dur * (p + r) / 2.0
        lo, hi = min(lo, q), max(hi, q)
    return hi - lo
