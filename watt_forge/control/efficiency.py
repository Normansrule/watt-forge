"""Converter-side controls that raise efficiency, evaluated on the flagship loss model.

    adaptive switching frequency   pick the loss-minimising f_s online (Al-Hoor et al. 2009)
    adaptive dead time             pick the loss-minimising dead time online (Yousefzadeh & Maksimovic 2006)
    burst mode                     at light load, run in bursts at an efficient power and idle between
                                   them (pulse skipping, Peterchev & Sanders 2006)
    bypass                         tie panel to battery when the MPP sits at battery voltage
                                   (flagship hardware, watt_forge/flagship/model.py::bypass)

The online optimisers (frequency, dead time) are one portable state machine, HillClimb: it probes
a neighbouring setting, keeps it if the measured power fell by more than a margin, and otherwise
turns around. It uses only power measurements, at the resolution the converter's sensors allow
after averaging (power_sigma). Here it is driven by the loss model plus that measurement noise, and
results are averaged over MC_SEEDS noise seeds. Burst mode and bypass are not online optimisers:
their parameters are design-time choices made with the model. The JavaScript and C ports run the
same HillClimb.

Every number below is a model prediction. The ESTIMATE-tagged inputs (wake energy, input
capacitance) are explained where they are defined. REFERENCE ONLY.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, List, Optional

from .. import pv
from ..flagship import model
from ..flagship.params import Params
from .rng import XorShift32

FIXED_FS = 100e3                 # Hz: a common fixed choice for a 400 W GaN stage
TD_GRID = [k * 1e-9 for k in range(4, 51, 2)]   # 4, 6 ... 50 ns: includes the 10 ns design value; 4 ns floor
                                                # for driver/propagation mismatch; 2 ns steps, because near the
                                                # optimum a 1 ns step changes the loss by less than an averaged
                                                # power measurement resolves
BURST_POWERS = (40.0, 60.0, 90.0, 120.0, 160.0)   # W: candidate power levels to burst at
BURST_FREQS = (250.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0)   # Hz candidates for the burst repetition rate
BURST_MIN_CYCLES = 8             # each burst must last at least this many switching periods
E_WAKE = 4e-6                    # J per burst start. ESTIMATE: driver/bootstrap wake-up, inductor
                                 # current build-up and flying-capacitor rebalancing
C_IN_BULK = 66e-6                # F: 2x 33 uF electrolytic (BOM), little DC-bias loss
C_IN_MLCC_N, C_IN_MLCC_EACH = 6, 10e-6          # 6x 10 uF X7S MLCC (BOM), derated with DC bias
BURST_MAX_RIPPLE = 0.05          # burst ripple on the panel limited to 5 % of Vin: beyond that the
                                 # second-order mismatch estimate (and the MPPT itself) stop being valid

# Online optimisers measure power with the same sensors as the MPPT bench: sigma 20 mV and 10 mA per
# 20 ms tick (already averaged within the tick, see bench.py). Each comparison averages AVG_SAMPLES
# ticks: 5 s, affordable because the best frequency and dead time drift slowly. Settings are compared
# back to back at a fixed operating point, so slow irradiance drift largely cancels; fast flicker does
# not, and is not modelled. The resulting resolution, and the 2-sigma acceptance margin, are what limit
# how close the hill climb gets to the optimum.
SIGMA_V_SAMPLE, SIGMA_I_SAMPLE = 0.02, 0.01
AVG_SAMPLES = 250
MC_SEEDS = 20                    # noise seeds per operating point; results are means over them

# Panel-curvature estimate for converter-only maps (no panel model at that point): the 72-cell
# reference panel has kappa = 3.76 W/V^2 at 364.8 W, 37.6 V (1000 W/m^2, 40 C). For a panel of the
# same technology scaled to another MPP voltage, kappa ~ P / V^2.
KAPPA_REF, P_KAPPA_REF, V_KAPPA_REF = 3.76, 364.8, 37.6


# ------------------------------------------------------------ helpers on the loss model
def _feasible_best(rs: List[Dict]) -> Optional[Dict]:
    ok = [r for r in rs if r["feasible"]]
    return min(ok, key=lambda r: r["loss_total"]) if ok else None


def at(vin: float, vout: float, pout: float, fs: float, td: Optional[float] = None, p: Optional[Params] = None) -> Optional[Dict]:
    """Best feasible mode at a given frequency (and dead time)."""
    p = p or Params()
    if td is not None:
        p = replace(p, t_dead=td)
    return _feasible_best([model.evaluate(vin, vout, pout, fs, m, p) for m in model.modes_for(vin, vout)])


def fs_curve(vin: float, vout: float, pout: float, td: Optional[float] = None, p: Optional[Params] = None) -> List[Dict]:
    p = p or Params()
    out = []
    for fs in p.f_candidates:
        r = at(vin, vout, pout, fs, td, p)
        out.append({"fs": fs, "loss": r["loss_total"] if r else None, "mode": r["mode"] if r else None})
    return out


def fixed_fs(vin: float, vout: float, pout: float, td: Optional[float] = None, p: Optional[Params] = None) -> Dict:
    """Fixed 100 kHz; where the ripple limits forbid it, the lowest feasible frequency above."""
    p = p or Params()
    for fs in [f for f in p.f_candidates if f >= FIXED_FS]:
        r = at(vin, vout, pout, fs, td, p)
        if r:
            return r
    raise ValueError("no feasible frequency")


def td_curve(vin: float, vout: float, pout: float, fs: float, p: Optional[Params] = None) -> List[Dict]:
    p = p or Params()
    out = []
    for td in TD_GRID:
        r = at(vin, vout, pout, fs, td, p)
        out.append({"td": td, "loss": r["loss_total"] if r else None})
    return out


# ------------------------------------------------------------ the online optimiser
class HillClimb:
    """Discrete extremum seeking over an ordered list of settings (frequencies or dead times).

    Each update receives the measured cost (input power at constant output power) for the
    setting currently applied and returns the index to apply next. A move is kept only if it
    lowers the cost by more than `margin` (2 sigma of the measurement in operating_point), which
    makes noise-driven moves rare but not impossible, and stops the climb where the remaining gain
    is below the measurement resolution. After a
    failed probe in both directions it rests for `rest` updates, then probes again (operating
    points drift, so the search never stops for good)."""

    def __init__(self, n: int, start: int, margin: float = 0.02, rest: int = 10):
        self.n, self.idx, self.margin, self.rest = n, start, margin, rest
        self.base_cost = -1.0
        self.probe = 0          # 0: measuring the base, +1/-1: measuring a neighbour
        self.direction = 1
        self.fails = 0
        self.resting = 0

    def update(self, cost: float) -> int:
        if self.resting > 0:
            self.resting -= 1
            if self.resting == 0:
                self.base_cost = -1.0
            return self.idx
        if self.probe == 0:
            self.base_cost = cost
            nxt = self.idx + self.direction
            if nxt < 0 or nxt >= self.n:
                self.direction = -self.direction
                nxt = self.idx + self.direction
            self.probe = self.direction
            self.idx = nxt
            return self.idx
        # we were measuring a neighbour
        if cost < self.base_cost - self.margin:
            self.base_cost = cost
            self.fails = 0
            self.probe = 0          # accept, keep going the same way next time
            return self.idx
        self.idx -= self.probe      # reject: go back
        self.probe = 0
        self.direction = -self.direction
        self.fails += 1
        if self.fails >= 2:
            self.fails = 0
            self.resting = self.rest
        return self.idx


def online_search(costs: List[Optional[float]], start: int, updates: int = 60, sigma: float = 0.03,
                  seed: int = 3, margin: float = 0.02) -> Dict:
    """Run HillClimb against a cost table (None = infeasible, treated as very costly) with
    Gaussian-like measurement noise. Returns the trajectory and where it ends up."""
    rng = XorShift32(seed)
    hc = HillClimb(len(costs), start, margin=margin)
    idx = start
    path = [idx]
    for _ in range(updates):
        c = costs[idx]
        c = 1e9 if c is None else c + sigma * rng.normal()
        idx = hc.update(c)
        path.append(idx)
    # where it spends its time at the end (the probe excursions are short); ties -> lower index
    tail = path[-20:]
    counts = [tail.count(i) for i in range(len(costs))]
    final = max(range(len(costs)), key=lambda i: (counts[i], -i))
    return {"path": path, "final": final}


def power_sigma(vin: float, pin: float) -> float:
    """Standard deviation of one averaged input-power comparison (W)."""
    i = pin / vin
    per_sample = math.sqrt((i * SIGMA_V_SAMPLE) ** 2 + (vin * SIGMA_I_SAMPLE) ** 2)
    return per_sample / math.sqrt(AVG_SAMPLES)


def kappa_estimate(vin: float, pout: float) -> float:
    """P-V curvature at the MPP for a panel of the reference technology at this voltage and power."""
    return KAPPA_REF * (pout / P_KAPPA_REF) * (V_KAPPA_REF / vin) ** 2


def monte_carlo(costs: List[Optional[float]], start: int, sigma: float, seeds: int = MC_SEEDS, seed0: int = 1) -> Dict:
    """HillClimb over many noise seeds: where it lands, how often it finds the optimum, and the
    mean cost of where it lands (the honest figure for a noisy online optimiser)."""
    finals, paths = [], []
    for k in range(seeds):
        r = online_search(costs, start, sigma=sigma, margin=2.0 * sigma, seed=seed0 + k)
        finals.append(r["final"])
        paths.append(r["path"])
    opt = min((i for i, c in enumerate(costs) if c is not None), key=lambda i: costs[i])
    mean = sum(costs[f] for f in finals) / len(finals)
    counts = [finals.count(i) for i in range(len(costs))]
    mode = max(range(len(costs)), key=lambda i: (counts[i], -i))
    return {"finals": finals, "mode": mode, "optimum": opt, "hit_rate": counts[opt] / len(finals),
            "mean_cost": mean, "path": paths[0]}


# ------------------------------------------------------------ burst mode
def c_in(vin: float, p: Optional[Params] = None) -> float:
    """Input capacitance after DC-bias derating of the MLCCs (F)."""
    p = p or Params()
    return C_IN_BULK + C_IN_MLCC_N * C_IN_MLCC_EACH * _bias(p, vin)


def _bias(p: Params, v: float) -> float:
    """DC-bias capacitance factor of the 100 V X7S MLCCs (same curve as the flying capacitors)."""
    pts = p.cfly_bias_curve
    if v <= pts[0][0]:
        return pts[0][1]
    for (v0, k0), (v1, k1) in zip(pts, pts[1:]):
        if v0 <= v <= v1:
            return k0 + (k1 - k0) * (v - v0) / (v1 - v0)
    return pts[-1][1]


def pv_curvature(vmp: float, g: float, tc: float, panel: Optional[pv.Panel] = None, h: float = 0.25) -> float:
    """|d2P/dV2| at the MPP, by central difference on the panel model (W/V^2)."""
    panel = panel or pv.Panel()
    f = lambda v: v * pv.panel_current(v, [g] * 3, tc, panel)  # noqa: E731
    return abs(f(vmp + h) - 2.0 * f(vmp) + f(vmp - h)) / (h * h)


def burst(vin: float, vout: float, pout: float, kappa: float, p: Optional[Params] = None) -> Dict:
    """Burst mode at average output `pout`: switch at a burst power P_b for a fraction delta of the
    time, idle otherwise. Losses = delta x stage loss at the burst power + housekeeping (full
    while switching, idle level otherwise) + wake energy x burst rate + MPPT mismatch from the
    input-capacitor ripple. The panel keeps delivering its current, so the input capacitor charges
    between bursts: dV_pp = I_pv (1 - delta) / (f_b C_in), which moves the panel off its MPP
    by a triangular ripple. Mismatch loss ~ (1/2) kappa <dV^2> = kappa dV_pp^2 / 24.
    The burst power (BURST_POWERS) and burst rate (BURST_FREQS) are chosen together: a high burst
    power runs the stage near its best efficiency but leaves long gaps (more input ripple); a low
    one does the opposite."""
    p = p or Params()
    i_pv = (pout + 1.0) / vin           # ~ panel current (output plus about a watt of loss)
    cin = c_in(vin, p)
    best = None
    for pb in BURST_POWERS:
        if pout >= 0.9 * pb:
            continue
        rb = model.best(vin, vout, pb, p)
        delta = pout / pb
        stage_b = rb["loss_stage"]
        aux = delta * p.p_aux_switching + (1.0 - delta) * p.p_aux_idle
        for fb in BURST_FREQS:
            if delta / fb < BURST_MIN_CYCLES / rb["fs"]:
                continue                # bursts too short to be worth starting
            dv = i_pv * (1.0 - delta) / (fb * cin)
            if dv > BURST_MAX_RIPPLE * vin:
                continue                # too much panel ripple for the small-signal estimate
            mismatch = kappa * dv * dv / 24.0
            wake = E_WAKE * fb
            loss = delta * stage_b + aux + wake + mismatch
            cand = {"active": True, "p_burst": pb, "f_burst": fb, "fs_burst": rb["fs"], "delta": delta, "dv_pp": dv,
                    "loss_total": loss, "parts": {"stage": delta * stage_b, "aux": aux, "wake": wake, "mismatch": mismatch},
                    "eta": pout / (pout + loss)}
            if best is None or loss < best["loss_total"]:
                best = cand
    return best or {"active": False}


# ------------------------------------------------------------ one operating point, all strategies
def operating_point(vin: float, vout: float, pout: float, kappa: float = 0.0, p: Optional[Params] = None) -> Dict:
    """Losses at one operating point under each control strategy, applied cumulatively:
    base (fixed 100 kHz, fixed design dead time) -> +adaptive f_s -> +adaptive dead time -> +burst -> +bypass.

    Adaptive f_s and dead time are online hill climbs with realistic measurement resolution
    (power_sigma); their losses are means over MC_SEEDS noise seeds. Burst parameters and the
    bypass band are design-time choices made with the model. The feasible frequency range (ripple
    limits) is likewise a design-time bound handed to the controller."""
    p = p or Params()
    base = fixed_fs(vin, vout, pout, None, p)
    sigma = power_sigma(vin, pout + base["loss_total"])
    # adaptive frequency: HillClimb over the candidate list, starting at 100 kHz
    curve = fs_curve(vin, vout, pout, None, p)
    costs = [c["loss"] for c in curve]
    start = list(p.f_candidates).index(FIXED_FS)
    mf = monte_carlo(costs, start, sigma)
    fs_on = p.f_candidates[mf["mode"]]
    # adaptive dead time, searched at the frequency the climb most often settles on
    tdc = td_curve(vin, vout, pout, fs_on, p)
    tcosts = [c["loss"] for c in tdc]
    t_start = min(range(len(TD_GRID)), key=lambda i: abs(TD_GRID[i] - p.t_dead))
    mt = monte_carlo(tcosts, t_start, sigma, seed0=101)
    # cumulative mean loss after the dead-time climb = loss at the chosen f_s, shifted by what the
    # dead-time climb gains on average relative to the design dead time at that frequency
    loss_fs = mf["mean_cost"]
    loss_td = loss_fs + (mt["mean_cost"] - tcosts[t_start])
    # burst mode at light load (only if it beats continuous switching)
    b = burst(vin, vout, pout, kappa, p) if kappa > 0 else {"active": False}
    loss_burst = min(loss_td, b["loss_total"]) if b.get("active") else loss_td
    # bypass when the panel MPP sits within 2 % of the battery: the panel is then pinned at battery
    # voltage, which costs (1/2) kappa (Vin - Vout)^2 of MPPT mismatch on top of the conduction loss
    loss_bypass = loss_burst
    bypass_mismatch = 0.0
    if abs(vin - vout) <= 0.02 * vout:
        bypass_mismatch = 0.5 * kappa * (vin - vout) ** 2
        loss_bypass = min(loss_burst, model.bypass(vin, pout, p)["loss_total"] + bypass_mismatch)
    return {
        "vin": vin, "vout": vout, "pout": pout, "sigma": sigma,
        "loss": {"base": base["loss_total"], "fs": loss_fs, "td": loss_td, "burst": loss_burst, "bypass": loss_bypass},
        "fs": {"fixed": base["fs"], "online": fs_on, "optimum": p.f_candidates[mf["optimum"]], "hit_rate": mf["hit_rate"],
               "path": mf["path"], "finals": mf["finals"]},
        "td": {"fixed": p.t_dead, "online": TD_GRID[mt["mode"]], "optimum": TD_GRID[mt["optimum"]], "hit_rate": mt["hit_rate"],
               "path": mt["path"], "finals": mt["finals"], "loss_fixed": tcosts[t_start]},
        "burst": b, "bypass_mismatch": bypass_mismatch,
    }


# ------------------------------------------------------------ a day of sun
def clear_day(step_min: int = 10) -> List[Dict]:
    """06:00-18:00 clear sky with a cloudy hour around 13:00. Irradiance follows a sine of the
    solar hour (peak 950 W/m^2). Air temperature runs 16 -> 27 C. Cell temperature uses the
    NOCT model: Tc = Ta + G (45 - 20) / 800."""
    out = []
    for m in range(6 * 60, 18 * 60 + 1, step_min):
        h = m / 60.0
        s = math.sin(math.pi * (h - 6.0) / 12.0)
        g = 950.0 * s ** 1.3 if s > 0 else 0.0
        if 12.5 <= h < 13.5:
            g *= 0.35
        ta = 16.0 + 11.0 * math.sin(math.pi * (h - 8.0) / 14.0) if h >= 8.0 else 16.0
        out.append({"h": h, "g": g, "ta": ta, "tc": ta + g * 25.0 / 800.0})
    return out


def daily_energy(eta_mppt: float, vout: float = 51.2, step_min: int = 10, p: Optional[Params] = None) -> Dict:
    """Energy waterfall for one day: available at the MPP -> after MPPT -> delivered, with the
    conversion loss under each cumulative control strategy. Energies in Wh."""
    p = p or Params()
    panel = pv.Panel()
    dt_h = step_min / 60.0
    e = {"available": 0.0, "after_mppt": 0.0, "base": 0.0, "fs": 0.0, "td": 0.0, "burst": 0.0, "bypass": 0.0}
    rows = []
    for env in clear_day(step_min):
        if env["g"] < 20.0:
            continue
        mpp = pv.global_mpp([env["g"]] * 3, env["tc"], panel)
        vmp, pmp = mpp["v"], mpp["p"]
        if vmp < p.spec.vin_min:
            continue
        pin = pmp * eta_mppt
        # convert input power to output power at this point: iterate pout = pin - loss(pout)
        kappa = pv_curvature(vmp, env["g"], env["tc"], panel)
        pout = 0.98 * pin
        for _ in range(4):
            op = operating_point(vmp, vout, pout, kappa, p)
            pout = pin - op["loss"]["base"]
        e["available"] += pmp * dt_h
        e["after_mppt"] += pin * dt_h
        row = {"h": env["h"], "g": env["g"], "vmp": vmp, "pmp": pmp}
        for k in ("base", "fs", "td", "burst", "bypass"):
            loss = op["loss"][k]
            e[k] += max(pin - loss, 0.0) * dt_h
            row[k] = loss
        rows.append(row)
    return {"energy_Wh": e, "rows": rows, "eta_mppt": eta_mppt, "vout": vout, "step_min": step_min}
