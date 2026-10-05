"""Maximum power point tracking (MPPT) algorithms behind one interface.

Every tracker commands the panel-voltage reference `vref`. The bench calls `update(v, i)` once
every `period` plant ticks with the averaged, noisy measurements, and reads `vref` back.
A tracker may set `open_request = True` to ask for one open-circuit tick (fractional Voc does).

    key      algorithm                                   family        reference
    po       perturb and observe, fixed step             hill climbing Femia et al. 2005
    vspo     perturb and observe, variable step          hill climbing Femia et al. 2005
    inc      incremental conductance, fixed step         hill climbing Hussein et al. 1995
    vsinc    incremental conductance, variable step      hill climbing Liu et al. 2008
    focv     fractional open-circuit voltage             model based   Masoum et al. 2002
    esc      extremum seeking (injected dither)          gradient      Leyva et al. 2006; Esram et al. 2006 (RCC)
    pso      particle swarm, then variable-step P&O      global search Miyatake et al. 2011
    scan     global scan, then variable-step P&O         global search Patel & Agarwal 2008

All arithmetic is plain floating point in a fixed order, and the only randomness is the shared
xorshift32 generator, so the JavaScript (docs/js/model/mppt.js) and C (hardware/flagship/control/
wf_mppt.c) ports reproduce these trackers decision for decision. REFERENCE ONLY.
"""
from __future__ import annotations

from typing import Dict, List

from .rng import XorShift32

V_MIN, V_MAX = 12.0, 60.0   # flagship input-voltage window


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


class Tracker:
    key = "base"
    name = "base"
    period = 2

    def __init__(self, **kw):
        for k, v in kw.items():
            if not hasattr(self, k):
                raise TypeError(f"{type(self).__name__} has no parameter {k!r}")
            setattr(self, k, v)
        self.vref = 0.0
        self.open_request = False
        self.voc = 0.0

    def hi(self) -> float:
        # upper voltage limit from the Voc measured at reset (only FOCV re-measures it); the
        # profiles keep Vmpp far below 0.98 Voc0, so the stale value never binds here
        h = 0.98 * self.voc
        return h if h < V_MAX else V_MAX

    def reset(self, voc: float):
        self.voc = voc
        self.vref = _clamp(0.8 * voc, V_MIN, self.hi())

    def update(self, v: float, i: float):  # pragma: no cover - abstract
        raise NotImplementedError

    def params(self) -> Dict[str, float]:
        return {k: getattr(self, k) for k in getattr(self, "PARAMS", ())}


# ---------------------------------------------------------------- hill climbing
class PO(Tracker):
    """Perturb and observe, fixed step: keep going while power rises, reverse when it falls."""
    key, name = "po", "Perturb & observe (fixed step)"
    PARAMS = ("step", "period")
    step = 0.2           # tuned (data/mppt_tuned.json)
    period = 1

    def reset(self, voc):
        super().reset(voc)
        self.p_prev = -1.0
        self.direction = -1.0

    def update(self, v, i):
        p = v * i
        if self.p_prev >= 0.0 and p < self.p_prev:
            self.direction = -self.direction
        self.p_prev = p
        self.vref = _clamp(self.vref + self.direction * self.step, V_MIN, self.hi())


class VSPO(Tracker):
    """Perturb and observe with a step proportional to |dP/dV|: big steps far from the
    maximum power point (MPP), small steps near it."""
    key, name = "vspo", "Perturb & observe (variable step)"
    PARAMS = ("gain", "step_min", "step_max", "period")
    gain = 0.04          # V per (W/V), tuned
    step_min = 0.3       # V, tuned
    step_max = 2.0       # V
    period = 2

    def reset(self, voc):
        super().reset(voc)
        self.p_prev = -1.0
        self.v_prev = 0.0
        self.direction = -1.0
        self.step = 0.5

    def update(self, v, i):
        p = v * i
        if self.p_prev >= 0.0:
            dv = v - self.v_prev
            dp = p - self.p_prev
            if dp < 0.0:
                self.direction = -self.direction
            if dv > 0.05 or dv < -0.05:
                slope = dp / dv
                if slope < 0.0:
                    slope = -slope
                self.step = _clamp(self.gain * slope, self.step_min, self.step_max)
        self.p_prev, self.v_prev = p, v
        self.vref = _clamp(self.vref + self.direction * self.step, V_MIN, self.hi())


class INC(Tracker):
    """Incremental conductance: at the MPP dP/dV = 0, i.e. dI/dV = -I/V. Compare the two and
    step toward the MPP; hold still when they agree to within a tolerance."""
    key, name = "inc", "Incremental conductance (fixed step)"
    PARAMS = ("step", "tol", "period")
    step = 0.3           # tuned
    tol = 0.001          # relative tolerance on dI/dV + I/V, tuned
    period = 2

    def reset(self, voc):
        super().reset(voc)
        self.first = True
        self.v_prev = 0.0
        self.i_prev = 0.0
        self.vref = self.vref - self.step

    def _direction(self, v, i):
        """+1: MPP is at higher voltage, -1: lower, 0: hold."""
        dv = v - self.v_prev
        di = i - self.i_prev
        g = i / v if v > 1.0 else 0.0
        if -0.05 < dv < 0.05:          # voltage did not move: irradiance change shows up in dI
            if -0.02 < di < 0.02:
                return 0.0
            return 1.0 if di > 0.0 else -1.0
        e = di / dv + g                # = (dP/dV) / V
        if -self.tol * g < e < self.tol * g:
            return 0.0
        return 1.0 if e > 0.0 else -1.0

    def update(self, v, i):
        if not self.first:
            d = self._direction(v, i)
            self.vref = _clamp(self.vref + d * self._step(v, i), V_MIN, self.hi())
        self.first = False
        self.v_prev, self.i_prev = v, i

    def _step(self, v, i):
        return self.step


class VSINC(INC):
    """Variable-step incremental conductance: step = N |dP/dV| (Liu et al. 2008)."""
    key, name = "vsinc", "Incremental conductance (variable step)"
    PARAMS = ("gain", "step_min", "step_max", "tol", "period")
    gain = 0.08          # tuned
    step_min = 0.3       # tuned
    step_max = 2.0
    tol = 0.03
    step = 0.5           # initial offset only
    period = 2

    def _step(self, v, i):
        dv = v - self.v_prev
        if -0.05 < dv < 0.05:
            return self.step_min
        slope = (v * i - self.v_prev * self.i_prev) / dv
        if slope < 0.0:
            slope = -slope
        return _clamp(self.gain * slope, self.step_min, self.step_max)


# ---------------------------------------------------------------- model based
class FOCV(Tracker):
    """Fractional open-circuit voltage: Vmpp ~ k Voc. Every `every` updates the converter stops
    for one tick to measure Voc (that tick harvests nothing), then regulates to k Voc.
    Cheap and robust, but k drifts with irradiance and temperature, so it never sits exactly
    on the MPP."""
    key, name = "focv", "Fractional open-circuit voltage"
    PARAMS = ("k", "every", "period")
    k = 0.84             # tuned
    every = 1000         # updates between Voc samples (20 s at 50 Hz), tuned
    period = 1

    def reset(self, voc):
        super().reset(voc)
        self.count = 0
        self.vref = _clamp(self.k * voc, V_MIN, self.hi())
        self.sampling = False

    def update(self, v, i):
        if self.sampling:                  # this tick was open circuit: v is Voc
            self.sampling = False
            self.open_request = False
            self.voc = v
            self.vref = _clamp(self.k * v, V_MIN, self.hi())
            return
        self.count += 1
        if self.count >= self.every:
            self.count = 0
            self.sampling = True
            self.open_request = True


# ---------------------------------------------------------------- gradient
SIN10 = (0.0, 0.5877852522924731, 0.9510565162951535, 0.9510565162951536, 0.5877852522924732,
         1.2246467991473532e-16, -0.587785252292473, -0.9510565162951535, -0.9510565162951536,
         -0.5877852522924734)   # sin(2 pi k / 10), written out so every port uses the same doubles


class ESC(Tracker):
    """Extremum seeking: add a small sinusoidal dither to the voltage, high-pass the power,
    multiply by the dither (demodulate) and integrate. The product averages to a value
    proportional to dP/dV ((a/2) dP/dV with an ideal high-pass; this first-order filter's gain and
    phase at the dither make it about 0.8 of that), so the integrator climbs the power curve
    (Leyva et al. 2006). Ripple correlation control (RCC) is the same idea with the converter's own
    switching ripple as the dither (Esram et al. 2006); at a 50 Hz plant rate this model injects a
    5 Hz dither instead."""
    key, name = "esc", "Extremum seeking (injected dither)"
    PARAMS = ("amp", "gain", "hp", "period")
    amp = 0.8            # V dither amplitude, tuned
    gain = 0.016         # V per (W * dither) per update, tuned
    hp = 0.8             # high-pass pole (per update)
    period = 1

    def reset(self, voc):
        super().reset(voc)
        self.vhat = self.vref
        self.k = 0
        self.p_prev = -1.0
        self.hpf = 0.0

    def update(self, v, i):
        p = v * i
        if self.p_prev >= 0.0:
            self.hpf = self.hp * (self.hpf + p - self.p_prev)
        self.p_prev = p
        # the measurement belongs to the dither applied on the previous update
        self.vhat = _clamp(self.vhat + self.gain * self.hpf * SIN10[self.k], V_MIN, self.hi())
        self.k = (self.k + 1) % 10
        self.vref = _clamp(self.vhat + self.amp * SIN10[self.k], V_MIN, self.hi())


# ---------------------------------------------------------------- global search
class PSO(Tracker):
    """Particle swarm optimisation over the panel voltage, then variable-step P&O.

    Four particles start spread across the voltage window. Each is held for one update while
    its power is measured. After every sweep of the swarm the standard PSO velocity update
    pulls particles toward their own best and the swarm's best. When they agree to within
    0.5 V (or after 15 iterations) the tracker hands over to variable-step P&O. A power change
    of more than `restart` (25 %, tuned) either way restarts the swarm, because shading may have
    moved the global MPP. The random numbers come from the seeded xorshift32, so runs repeat exactly."""
    key, name = "pso", "Particle swarm + variable-step P&O"
    PARAMS = ("n", "w", "c1", "c2", "restart", "period")
    n = 4
    w = 0.4
    c1 = 1.0
    c2 = 1.6
    restart = 0.25       # tuned (w = 0.4 also tuned)
    period = 2

    def __init__(self, seed: int = 12345, **kw):
        super().__init__(**kw)
        self.rng = XorShift32(seed)
        self.local = VSPO()

    def _spread(self):
        lo, hi = V_MIN, self.hi()
        self.x = [lo + (hi - lo) * (j + 0.5) / self.n for j in range(self.n)]
        self.vel = [0.0] * self.n
        self.pbest = [-1.0] * self.n
        self.xbest = list(self.x)
        self.gbest_p = -1.0
        self.gbest_x = self.x[0]
        self.j = 0
        self.iters = 0
        self.searching = True
        self.vref = self.x[0]

    def reset(self, voc):
        super().reset(voc)
        self._spread()
        self.p_track = 0.0

    def update(self, v, i):
        p = v * i
        if self.searching:
            if p > self.pbest[self.j]:
                self.pbest[self.j], self.xbest[self.j] = p, self.x[self.j]
            if p > self.gbest_p:
                self.gbest_p, self.gbest_x = p, self.x[self.j]
            self.j += 1
            if self.j >= self.n:
                self.j = 0
                self.iters += 1
                spread = 0.0
                lo, hi = V_MIN, self.hi()
                for k in range(self.n):
                    r1, r2 = self.rng.uniform(), self.rng.uniform()
                    self.vel[k] = (self.w * self.vel[k] + self.c1 * r1 * (self.xbest[k] - self.x[k])
                                   + self.c2 * r2 * (self.gbest_x - self.x[k]))
                    self.x[k] = _clamp(self.x[k] + self.vel[k], lo, hi)
                    d = self.x[k] - self.gbest_x
                    if d < 0.0:
                        d = -d
                    if d > spread:
                        spread = d
                if spread < 0.5 or self.iters >= 15:
                    self.searching = False
                    self.local.reset(self.voc)
                    self.local.vref = self.gbest_x
                    self.vref = self.gbest_x
                    self.p_track = self.gbest_p
                    return
            self.vref = self.x[self.j]
            return
        # tracking with variable-step P&O; restart the swarm on a large power change
        if self.p_track > 1.0:
            ratio = p / self.p_track
            if ratio < 1.0 - self.restart or ratio > 1.0 + self.restart:
                self._spread()
                return
        self.p_track = 0.98 * self.p_track + 0.02 * p
        self.local.update(v, i)
        self.vref = self.local.vref


class SCAN(Tracker):
    """Global scan, then variable-step P&O: sweep the voltage window from high to low, park at
    the best point, track locally. Re-scan every `rescan` updates, or when power falls below
    `drop` x its running average (shading or a cloud edge). This is the flagship controller's
    strategy (watt_forge/flagship/control.py) in library form."""
    key, name = "scan", "Global scan + variable-step P&O"
    PARAMS = ("points", "lo_frac", "rescan", "drop", "period")
    points = 8           # tuned; also the design floor: a three-substring panel's peaks are ~Voc/3
                         # apart, so 8 points (~4.5 V spacing) cannot step over one
    lo_frac = 0.25
    rescan = 1500        # updates (60 s at period 2)
    drop = 0.45          # tuned
    period = 2

    def __init__(self, **kw):
        super().__init__(**kw)
        self.local = VSPO()

    def _start(self):
        self.scanning = True
        self.k = 0
        self.best_p = -1.0
        self.best_v = 0.0
        self.top = self.hi()
        lo = self.lo_frac * self.voc
        self.bottom = lo if lo > V_MIN else V_MIN
        self.vref = self.top
        self.since = 0

    def reset(self, voc):
        super().reset(voc)
        self.p_avg = 0.0
        self._start()

    def update(self, v, i):
        p = v * i
        if self.scanning:
            if p > self.best_p:
                self.best_p, self.best_v = p, self.vref
            self.k += 1
            if self.k >= self.points:
                self.scanning = False
                self.local.reset(self.voc)
                self.local.vref = self.best_v
                self.vref = self.best_v
                self.p_avg = self.best_p
                return
            self.vref = self.top - (self.top - self.bottom) * self.k / (self.points - 1)
            return
        self.since += 1
        if self.since >= self.rescan or (self.p_avg > 20.0 and p < self.drop * self.p_avg):
            self._start()
            return
        self.p_avg = 0.97 * self.p_avg + 0.03 * p
        self.local.update(v, i)
        self.vref = self.local.vref


ALGORITHMS = {cls.key: cls for cls in (PO, VSPO, INC, VSINC, FOCV, ESC, PSO, SCAN)}
FAMILY = {"po": "Hill climbing", "vspo": "Hill climbing", "inc": "Hill climbing", "vsinc": "Hill climbing",
          "focv": "Model based", "esc": "Gradient (extremum seeking)", "pso": "Global search", "scan": "Global search"}
REFERENCE = {"po": "femia2005", "vspo": "femia2005", "inc": "hussein1995", "vsinc": "liu2008", "focv": "masoum2002",
             "esc": "leyva2006", "pso": "miyatake2011", "scan": "patel2008"}


def make(key: str, **kw) -> Tracker:
    return ALGORITHMS[key](**kw)


def keys() -> List[str]:
    return list(ALGORITHMS)
