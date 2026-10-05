"""Closed-loop MPPT bench: PV panel + input-voltage loop + noisy sensors, driven by a tracker.

Plant, per tick of DT = 20 ms:
    * the converter's input-voltage loop moves the panel voltage toward vref, closing a fraction
      ALPHA = 0.98 of the error per tick (first-order, tau ~ 5 ms), never above open circuit;
    * the panel current follows from the single-diode model with bypass diodes (watt_forge.pv);
    * sensors add Gaussian-like noise (sigma 20 mV, 10 mA, i.e. what is left after averaging the ADC samples in one tick) and 12-bit quantisation
      (0-72 V, 0-20 A full scale);
    * the tracker sees the average of the second half of each update period (settled samples).

Metrics (EN 50530 definition of dynamic MPPT efficiency):
    eta_mppt  = sum(P_pv dt) / sum(P_mpp dt), P_mpp the GLOBAL maximum available
    eta_sys   = energy delivered to the 48 V battery / sum(P_mpp dt), using the flagship
                converter efficiency table (so operating voltage matters, not just power)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from .. import pv
from . import mppt as M
from . import profiles as PR
from .rng import XorShift32

ALPHA = 0.98
SIGMA_V, SIGMA_I = 0.02, 0.01
LSB_V, LSB_I = 72.0 / 4096.0, 20.0 / 4096.0
ROOT = Path(__file__).resolve().parents[2]
ETA_TABLE_PATH = ROOT / "data" / "eta_table.json"


def quantize(x: float, lsb: float) -> float:
    q = math.floor(x / lsb + 0.5) * lsb
    return q if q > 0.0 else 0.0


# ------------------------------------------------------------ available power
class MppOracle:
    """Global maximum power point for an environment. Uniform irradiance uses a 2 W/m^2 grid with
    linear interpolation (error below 1e-5 relative for G >= 100 W/m^2, which every profile respects;
    it grows below ~60 W/m^2); non-uniform irradiance is solved exactly
    and cached. The JavaScript port uses the same scheme, so both see the same P_mpp."""

    STEP = 2.0

    def __init__(self, panel: Optional[pv.Panel] = None):
        self.panel = panel or pv.Panel()
        self.grids: Dict[float, List[float]] = {}
        self.cache: Dict[tuple, dict] = {}

    def _grid(self, t: float) -> List[float]:
        if t not in self.grids:
            n = int(1200 / self.STEP) + 1
            self.grids[t] = [0.0] + [pv.global_mpp([k * self.STEP] * 3, t, self.panel)["p"] for k in range(1, n)]
        return self.grids[t]

    def p_mpp(self, g: List[float], t: float) -> float:
        if g[0] == g[1] and g[1] == g[2]:
            grid = self._grid(t)
            x = g[0] / self.STEP
            k = int(math.floor(x))
            if k >= len(grid) - 1:
                return grid[-1]
            f = x - k
            return grid[k] + (grid[k + 1] - grid[k]) * f
        key = (g[0], g[1], g[2], t)
        if key not in self.cache:
            self.cache[key] = pv.global_mpp(g, t, self.panel)
        return self.cache[key]["p"]


# ------------------------------------------------------------ converter efficiency
class EtaTable:
    """Flagship converter efficiency eta(Vin, Pin) at Vout = 48 V, bilinear in (Vin, Pin).
    Built by build_eta_table() from the full loss model (watt_forge.flagship.model.best)."""

    def __init__(self, path: Path = ETA_TABLE_PATH):
        d = json.loads(Path(path).read_text())
        self.vins, self.pins, self.eta = d["vin"], d["pin"], d["eta"]

    def __call__(self, vin: float, pin: float) -> float:
        if pin <= 0.0:
            return 0.0
        vs, ps = self.vins, self.pins
        vin = vs[0] if vin < vs[0] else vs[-1] if vin > vs[-1] else vin
        if pin < ps[0]:
            # below the first grid power, the fixed (housekeeping) losses dominate:
            # eta falls in proportion to power
            return self(vin, ps[0]) * pin / ps[0]
        pin = ps[-1] if pin > ps[-1] else pin
        a = 0
        while a < len(vs) - 2 and vin > vs[a + 1]:
            a += 1
        b = 0
        while b < len(ps) - 2 and pin > ps[b + 1]:
            b += 1
        fa = (vin - vs[a]) / (vs[a + 1] - vs[a])
        fb = (pin - ps[b]) / (ps[b + 1] - ps[b])
        e = self.eta
        top = e[a][b] + (e[a][b + 1] - e[a][b]) * fb
        bot = e[a + 1][b] + (e[a + 1][b + 1] - e[a + 1][b]) * fb
        return top + (bot - top) * fa


def build_eta_table(vout: float = 48.0) -> dict:
    """eta(Vin, Pin) from the flagship loss model, Pin capped by the input-current limit."""
    from ..flagship import model
    from ..flagship.params import Params
    p = Params()
    vins = [float(v) for v in range(12, 61, 2)]
    pins = [2.0, 5.0, 10.0, 20.0, 35.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0]
    eta = []
    for vin in vins:
        row = []
        for pin in pins:
            # iterate on Pout so that Pout + losses = Pin
            pout = pin * 0.98
            for _ in range(6):
                r = model.best(vin, vout, pout, p)
                pout = pin * r["eta"]
            row.append(round(r["eta"], 7))
        eta.append(row)
    return {"_about": "Flagship converter efficiency at Vout = 48 V vs panel voltage and panel power, from "
                      "watt_forge.flagship.model.best (all losses incl. 0.55 W housekeeping). Generated by "
                      "scripts/make_control_data.py.", "vout": vout, "vin": vins, "pin": pins, "eta": eta}


# ------------------------------------------------------------ the run
def run(tracker: M.Tracker, profile: List[dict], seed: int = 7, noise: bool = True,
        oracle: Optional[MppOracle] = None, eta: Optional[EtaTable] = None, panel: Optional[pv.Panel] = None,
        record_every: int = 0, log: Optional[list] = None) -> Dict:
    """log, if given, receives every reset/update the tracker saw and its decision, for replaying
    into the C port: ('R', voc, vref, open) and ('U', v, i, vref, open)."""
    panel = panel or pv.Panel()
    oracle = oracle or MppOracle(panel)
    eta = eta or EtaTable()
    rng = XorShift32(seed)
    dt = PR.DT

    # tick 0: open circuit, so every tracker starts from a measured Voc
    env0 = profile[0]
    voc0 = pv.panel_voltage(0.0, env0["g"], env0["t"], panel)
    v = voc0
    tracker.reset(quantize(voc0, LSB_V))
    if log is not None:
        log.append(("R", quantize(voc0, LSB_V), tracker.vref, tracker.open_request))
    period = tracker.period
    settle = period // 2               # samples before this index in each window are discarded
    sum_v = sum_i = 0.0
    n_avg = 0
    tick_in_window = 0
    e_pv = e_mpp = e_batt = 0.0
    trace = {"t": [], "p": [], "pmpp": [], "v": []} if record_every else None
    for k, env in enumerate(profile):
        g, tc = env["g"], env["t"]
        voc = pv.panel_voltage(0.0, g, tc, panel)
        if tracker.open_request:
            v_true, i_true = voc, 0.0
        else:
            v = v + ALPHA * (tracker.vref - v)
            if v > voc:
                v = voc
            v_true = v
            i_true = pv.panel_current(v_true, g, tc, panel, iters=32)  # 3e-9 A resolution
        if tracker.open_request:
            v = voc                      # the input capacitor charged to Voc during the open tick
        p_true = v_true * i_true
        p_avail = oracle.p_mpp(g, tc)
        e_pv += p_true * dt
        e_mpp += p_avail * dt
        e_batt += p_true * eta(v_true, p_true) * dt
        if noise:
            vm = quantize(v_true + SIGMA_V * rng.normal(), LSB_V)
            im = quantize(i_true + SIGMA_I * rng.normal(), LSB_I)
        else:
            vm, im = v_true, i_true
        if trace is not None and k % record_every == 0:
            trace["t"].append(round(k * dt, 3))
            trace["p"].append(round(p_true, 3))
            trace["pmpp"].append(round(p_avail, 3))
            trace["v"].append(round(v_true, 3))
        if tracker.open_request:
            tracker.update(vm, im)       # the open-circuit sample goes straight to the tracker
            if log is not None:
                log.append(("U", vm, im, tracker.vref, tracker.open_request))
            sum_v = sum_i = 0.0
            n_avg = 0
            tick_in_window = 0
            continue
        if tick_in_window >= settle:
            sum_v += vm
            sum_i += im
            n_avg += 1
        tick_in_window += 1
        if tick_in_window >= period:
            tracker.update(sum_v / n_avg, sum_i / n_avg)
            if log is not None:
                log.append(("U", sum_v / n_avg, sum_i / n_avg, tracker.vref, tracker.open_request))
            sum_v = sum_i = 0.0
            n_avg = 0
            tick_in_window = 0
    out = {"eta_mppt": e_pv / e_mpp, "eta_sys": e_batt / e_mpp, "e_mpp_J": e_mpp, "e_pv_J": e_pv,
           "e_batt_J": e_batt, "e_lost_J": e_mpp - e_pv, "seconds": len(profile) * dt}
    if trace is not None:
        out["trace"] = trace
    return out


def benchmark(keys: Optional[List[str]] = None, profile_names: Optional[List[str]] = None, seed: int = 7,
              record_every: int = 0) -> Dict:
    keys = keys or M.keys()
    profile_names = profile_names or list(PR.PROFILES)
    panel = pv.Panel()
    oracle = MppOracle(panel)
    eta = EtaTable()
    res: Dict[str, Dict] = {}
    for name in profile_names:
        prof = PR.get(name)
        res[name] = {}
        for key in keys:
            res[name][key] = run(M.make(key), prof, seed=seed, oracle=oracle, eta=eta, panel=panel,
                                 record_every=record_every)
    return res
