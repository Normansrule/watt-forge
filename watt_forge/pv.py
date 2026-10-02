"""Photovoltaic (PV) panel model: single-diode cells grouped into substrings with bypass diodes.

Each substring obeys
    I = Iph - I0 * (exp((V + I*Rs)/a) - 1) - (V + I*Rs)/Rsh,   a = n * Ns * k*T/q
and a bypass diode clamps the substring to -V_bypass when the string current
exceeds what a shaded substring can carry. Partial shading therefore creates
several local power maxima, which is why the controller starts with a global sweep.

The default panel is a GENERIC 72-cell, ~400 W-class module (not a specific product).
All solvers use fixed-iteration bisection so the JavaScript port matches bit-for-bit
up to floating-point rounding.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Sequence

K_B = 1.380649e-23
Q_E = 1.602176634e-19


@dataclass
class Panel:
    isc_stc: float = 10.4        # A
    voc_stc: float = 49.5        # V (whole panel)
    n_cells: int = 72
    n_sub: int = 3               # substrings (one bypass diode each)
    ideality: float = 1.3
    rs_total: float = 0.30       # ohm
    rsh_total: float = 450.0     # ohm
    beta_voc: float = -0.0029    # 1/K
    alpha_isc: float = 0.0005    # 1/K
    v_bypass: float = 0.4        # V
    n_series: int = 1            # panels in series


def _sub_params(p: Panel, g: float, t_c: float):
    ns = p.n_cells // p.n_sub
    vt = K_B * (t_c + 273.15) / Q_E
    a = p.ideality * ns * vt
    rs = p.rs_total / p.n_sub
    rsh = p.rsh_total / p.n_sub
    voc_sub = p.voc_stc / p.n_sub * (1.0 + p.beta_voc * (t_c - 25.0))
    isc_t = p.isc_stc * (1.0 + p.alpha_isc * (t_c - 25.0))
    i0 = (isc_t - voc_sub / rsh) / (math.exp(voc_sub / a) - 1.0)
    iph = isc_t * max(g, 0.0) / 1000.0 * (1.0 + rs / rsh)
    return iph, i0, a, rs, rsh, voc_sub


def _i_of_v_sub(v: float, i: float, iph, i0, a, rs, rsh) -> float:
    """Residual form: returns f(V) = Iph - I0(e^{(V+I Rs)/a}-1) - (V+I Rs)/Rsh - I (decreasing in V)."""
    x = (v + i * rs) / a
    x = min(x, 200.0)
    return iph - i0 * (math.exp(x) - 1.0) - (v + i * rs) / rsh - i


def substring_voltage(i: float, g: float, t_c: float, p: Panel, iters: int = 40) -> float:
    """Substring voltage at current i. Newton's method started to the right of the root:
    the residual is decreasing and concave in V, so the iterates approach the root
    monotonically from above and never overshoot."""
    iph, i0, a, rs, rsh, voc = _sub_params(p, g, t_c)
    if _i_of_v_sub(-p.v_bypass, i, iph, i0, a, rs, rsh) < 0.0:
        return -p.v_bypass  # bypass diode carries the current
    v = voc * 1.1 + 1.0
    for _ in range(iters):
        x = min((v + i * rs) / a, 200.0)
        e = math.exp(x)
        g_v = iph - i0 * (e - 1.0) - (v + i * rs) / rsh - i
        dg = -i0 * e / a - 1.0 / rsh
        step = g_v / dg
        v -= step
        if -1e-12 < step < 1e-12:
            break
    return v


def panel_voltage(i: float, irradiance: Sequence[float], t_c: float, p: Panel) -> float:
    """Terminal voltage at string current i. irradiance has one entry per substring (W/m^2)."""
    v = 0.0
    for g in irradiance:
        v += substring_voltage(i, g, t_c, p)
    return v * p.n_series


def panel_current(v: float, irradiance: Sequence[float], t_c: float, p: Panel, iters: int = 50) -> float:
    """Current at terminal voltage v (inverts panel_voltage by bisection; V(I) is decreasing)."""
    i_max = p.isc_stc * 1.3 * max(1.0, max(irradiance) / 1000.0)
    if v <= panel_voltage(i_max, irradiance, t_c, p):
        return i_max
    lo, hi = 0.0, i_max
    if v >= panel_voltage(0.0, irradiance, t_c, p):
        return 0.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if panel_voltage(mid, irradiance, t_c, p) > v:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def pv_curve(irradiance: Sequence[float], t_c: float, p: Panel, n: int = 120) -> List[dict]:
    """Sample the P-V curve by sweeping the string current from 0 to just above Isc."""
    i_top = max(irradiance) / 1000.0 * p.isc_stc * (1 + p.alpha_isc * (t_c - 25)) * 1.02
    pts = []
    for k in range(n + 1):
        i = i_top * k / n
        v = panel_voltage(i, irradiance, t_c, p)
        if v < 0:
            continue
        pts.append({"v": v, "i": i, "p": v * i})
    pts.sort(key=lambda d: d["v"])
    return pts


def global_mpp(irradiance: Sequence[float], t_c: float, p: Panel, n: int = 200) -> dict:
    """Global maximum power point: dense current sweep then golden-section refinement."""
    pts = pv_curve(irradiance, t_c, p, n)
    best = max(pts, key=lambda d: d["p"])
    i_top = pts[0]["i"] if pts else 0.0
    step = (max(d["i"] for d in pts) or 1.0) / n
    lo, hi = max(0.0, best["i"] - step), best["i"] + step
    gr = (math.sqrt(5) - 1) / 2
    f = lambda i: i * panel_voltage(i, irradiance, t_c, p)  # noqa: E731
    c, d = hi - gr * (hi - lo), lo + gr * (hi - lo)
    for _ in range(40):
        if f(c) > f(d):
            hi = d
        else:
            lo = c
        c, d = hi - gr * (hi - lo), lo + gr * (hi - lo)
    i = 0.5 * (lo + hi)
    v = panel_voltage(i, irradiance, t_c, p)
    del i_top
    return {"v": v, "i": i, "p": v * i}
