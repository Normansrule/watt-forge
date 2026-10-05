"""Test profiles for MPPT algorithms, sampled at the plant tick (DT seconds).

Each profile is a list of environments {"g": [W/m^2 per substring], "t": cell temperature C}.

en50530_high / en50530_low
    Compressed versions of the EN 50530 (2010) dynamic MPPT test. The standard ramps irradiance
    between 30 % and 100 % of nominal (300 <-> 1000 W/m^2) at 10, 14, 20, 30, 50 and 100 W/m^2/s,
    and between 10 % and 50 % (100 <-> 500 W/m^2) at 0.5 ... 50 W/m^2/s, repeating slopes with
    longer dwells (repetition counts not verified here). Each sequence below keeps four of the
    standard slopes, one up-and-down trapezoid per slope, with 10 s dwells. It is not a compliance test.
clouds      cloud edges: fast drops and recoveries of irradiance at constant temperature
shading     partial shading of one, then two substrings (bypass diodes create local maxima)
steady      constant 800 W/m^2: start-up search plus steady-state tracking (oscillation, noise)
"""
from __future__ import annotations

import math
from typing import Dict, List

DT = 0.02  # s, plant tick (50 Hz)

HIGH_SLOPES = (10.0, 30.0, 50.0, 100.0)   # W/m^2/s, subset of the EN 50530 30-100 % sequence
LOW_SLOPES = (5.0, 10.0, 20.0, 50.0)      # W/m^2/s, subset of the EN 50530 10-50 % sequence
DWELL = 10.0                               # s

Env = Dict[str, object]


def _n(x: float) -> int:
    """Round half up (not Python's round-half-even), so the JS port builds identical profiles."""
    return int(math.floor(x + 0.5))


def _hold(g: float, seconds: float, t: float, out: List[Env]):
    for _ in range(_n(seconds / DT)):
        out.append({"g": [g, g, g], "t": t})


def _ramp(g0: float, g1: float, slope: float, t: float, out: List[Env]):
    n = _n(abs(g1 - g0) / slope / DT)
    for k in range(1, n + 1):
        g = g0 + (g1 - g0) * k / n
        out.append({"g": [g, g, g], "t": t})


def trapezoids(lo: float, hi: float, slopes, t: float = 25.0) -> List[Env]:
    out: List[Env] = []
    _hold(lo, DWELL, t, out)
    for s in slopes:
        _ramp(lo, hi, s, t, out)
        _hold(hi, DWELL, t, out)
        _ramp(hi, lo, s, t, out)
        _hold(lo, DWELL, t, out)
    return out


def clouds() -> List[Env]:
    """Cloud edges: (target W/m^2, transition seconds, hold seconds)."""
    seq = [(900, 0, 8), (250, 1.0, 6), (900, 2.0, 8), (400, 0.5, 5), (950, 0.8, 8),
           (150, 1.5, 6), (700, 3.0, 6), (300, 0.4, 4), (900, 1.0, 10)]
    out: List[Env] = []
    g = float(seq[0][0])
    for target, ramp_s, hold_s in seq:
        target = float(target)
        if ramp_s > 0:
            _ramp(g, target, abs(target - g) / ramp_s, 35.0, out)
        g = target
        _hold(g, hold_s, 35.0, out)
    return out


def shading() -> List[Env]:
    out: List[Env] = []
    for gs, seconds in (([900.0, 900.0, 900.0], 15), ([900.0, 900.0, 250.0], 25),
                        ([900.0, 450.0, 200.0], 25), ([900.0, 900.0, 900.0], 15)):
        for _ in range(_n(seconds / DT)):
            out.append({"g": list(gs), "t": 45.0})
    return out


def steady() -> List[Env]:
    out: List[Env] = []
    _hold(800.0, 30.0, 45.0, out)
    return out


def tuning() -> List[Env]:
    """Used ONLY to tune each algorithm's parameters (scripts/tune_mppt.py), never to score them:
    a ramp, a cloud edge, a second ramp, then a shading pattern unlike the one in `shading`."""
    out: List[Env] = []
    _hold(200.0, 3.0, 30.0, out)
    _ramp(200.0, 900.0, 25.0, 30.0, out)
    _hold(900.0, 5.0, 30.0, out)
    _ramp(900.0, 400.0, 500.0, 30.0, out)
    _hold(400.0, 5.0, 30.0, out)
    _ramp(400.0, 800.0, 40.0, 30.0, out)
    _hold(800.0, 5.0, 30.0, out)
    for _ in range(_n(15.0 / DT)):
        out.append({"g": [800.0, 300.0, 800.0], "t": 40.0})
    for _ in range(_n(10.0 / DT)):
        out.append({"g": [800.0, 800.0, 800.0], "t": 40.0})
    return out


PROFILES = {
    "en50530_high": ("EN 50530-style ramps, 300-1000 W/m² (10, 30, 50, 100 W/m²/s)",
                     lambda: trapezoids(300.0, 1000.0, HIGH_SLOPES)),
    "en50530_low": ("EN 50530-style ramps, 100-500 W/m² (5, 10, 20, 50 W/m²/s)",
                    lambda: trapezoids(100.0, 500.0, LOW_SLOPES)),
    "clouds": ("Cloud edges: fast drops and recoveries", clouds),
    "shading": ("Partial shading: one, then two substrings shaded", shading),
    "steady": ("Steady 800 W/m²: start-up plus steady tracking", steady),
}


def get(name: str) -> List[Env]:
    return PROFILES[name][1]()
