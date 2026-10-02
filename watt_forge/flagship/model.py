"""Analytic loss model of the flagship converter, edge by edge.

For an operating point (Vin, Vout, Pout) the model:
  1. picks the operating mode (buck / boost / buck-boost) allowed by the minimum pulse width,
  2. solves the duty cycles including resistive drops,
  3. reconstructs the exact ideal inductor-current waveform (piecewise linear),
  4. classifies every switching edge as hard or soft (zero-voltage switching, ZVS),
  5. sums every loss term, and
  6. repeats for each candidate switching frequency and keeps the lowest-loss feasible one.

The time-domain circuit simulation in ``sim.py`` re-derives the same operating
point from circuit equations (with dead time, reverse conduction and flying-capacitor
dynamics) and must agree with this model; see tests/test_flagship_sim.py.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from .. import devices, magnetics
from . import pwm
from .params import Params

MODES = ("buck", "boost", "buckboost")


def _r_sw(p: Params) -> float:
    return devices.get(p.switch).rds(p.tj) * p.dyn_rds


def _dcr_hot(p: Params) -> float:
    return p.dcr * (1.0 + p.dcr_tc * (p.t_ind - 25.0))


def _r_path(p: Params) -> float:
    """Series resistance in the inductor loop (four switches always conduct)."""
    return 4 * _r_sw(p) + _dcr_hot(p) + p.r_pcb


def duty_limits(p: Params, fs: float):
    dmin = (p.t_min_pulse + p.t_dead) * fs
    return dmin, 1.0 - dmin


def _solve_duties(mode: str, vin: float, vout: float, iout: float, fs: float, p: Params, phase: float):
    """Iterate duties and average inductor current (with ripple correlation) to convergence."""
    T = 1.0 / fs
    dmin, dmax = duty_limits(p, fs)
    rp = _r_path(p)
    in_active = mode in ("buck", "buckboost")
    out_active = mode in ("boost", "buckboost")
    il = iout * max(vout / vin, 1.0)
    d1, d2 = 1.0, 0.0
    w = None
    for _ in range(6):
        drop = il * rp
        if mode == "buck":
            d1, d2 = (vout + drop) / vin, 0.0
        elif mode == "boost":
            d1, d2 = 1.0, 1.0 - (vin - drop) / vout
        else:
            d1 = dmax
            d2 = 1.0 - (d1 * vin - drop) / vout
            if d2 < dmin:
                d2 = dmin
                d1 = ((1.0 - d2) * vout + drop) / vin
        segs, edges = pwm.build(d1, d2, phase, T, in_active, out_active)
        w = pwm.ideal_ripple(vin, vout, p.l, segs, edges, T)
        c_frac = pwm.frac(w, pwm.out_mask)
        corr = pwm.avg_i(w, 0.0, pwm.out_mask)  # <i~ * c>
        il = (iout - corr) / c_frac
    feasible = True
    reason = ""
    if in_active and not (dmin - 1e-12 <= d1 <= dmax + 1e-12):
        feasible, reason = False, f"buck duty {d1:.3f} outside [{dmin:.3f},{dmax:.3f}]"
    if out_active and not (dmin - 1e-12 <= d2 <= dmax + 1e-12):
        feasible, reason = False, f"boost duty {d2:.3f} outside [{dmin:.3f},{dmax:.3f}]"
    if mode == "buck" and d1 > dmax:
        feasible = False
    return d1, d2, il, w, feasible, reason


def evaluate(vin: float, vout: float, pout: float, fs: float, mode: str, p: Optional[Params] = None,
             phase: Optional[float] = None) -> Dict:
    """Full loss budget at one operating point, one mode, one frequency."""
    p = p or Params()
    dev = devices.get(p.switch)
    bds = devices.get(p.bds)
    iout = pout / vout
    in_active = mode in ("buck", "buckboost")
    out_active = mode in ("boost", "buckboost")

    # choose the leg phase shift that minimises RMS current (only matters when both legs switch)
    if phase is None:
        if mode == "buckboost":
            best = None
            for k in range(p.bb_phase_steps):
                ph = k / p.bb_phase_steps
                d1, d2, il, w, ok, why = _solve_duties(mode, vin, vout, iout, fs, p, ph)
                score = pwm.avg_i2(w, il)
                if best is None or score < best[0] - 1e-12:
                    best = (score, ph)
            phase = best[1]
        else:
            phase = 0.0
    d1, d2, il, w, feasible, reason = _solve_duties(mode, vin, vout, iout, fs, p, phase)

    r_sw = _r_sw(p)
    dcr = _dcr_hot(p)
    i2 = pwm.avg_i2(w, il)
    ac2 = i2 - il * il
    iin_dc = pwm.avg_i(w, il, pwm.in_mask)
    L: Dict[str, float] = {}
    L["switch_conduction"] = 4 * r_sw * i2
    L["inductor_dcr"] = dcr * il * il + dcr * ac2          # DC + ripple at DC resistance
    L["inductor_ac"] = dcr * (p.rac_factor - 1.0) * ac2    # extra winding loss of the ripple
    L["pcb_copper"] = p.r_pcb * i2
    L["shunts"] = p.r_shunt * (iin_dc * iin_dc + iout * iout)
    L["bds_disconnect"] = bds.rds(p.tj) * iin_dc * iin_dc
    cf = 0.0
    if in_active:
        cf += p.cfly_esr() * pwm.avg_i2(w, il, pwm.cf1_mask)
    if out_active:
        cf += p.cfly_esr() * pwm.avg_i2(w, il, pwm.cf2_mask)
    L["cfly_esr"] = cf
    i_in2 = pwm.avg_i2(w, il, pwm.in_mask)
    i_out2 = pwm.avg_i2(w, il, pwm.out_mask)
    L["cin_cout_esr"] = p.esr_in * max(i_in2 - iin_dc**2, 0.0) + p.esr_out * max(i_out2 - iout**2, 0.0)

    # --- switching edges
    coss = overlap = dead = hyst = ring = 0.0
    n_hard = 0
    t_on, t_off = dev.t_overlap(True), dev.t_overlap(False)
    for e in w.edges:
        i_e = pwm.edge_current(w, il, e)
        v = (vin if e.leg == "in" else vout) / 2.0
        q = dev.qoss(v)
        i_node_out = i_e if e.leg == "in" else -i_e
        hard = (i_node_out > 0) if e.incoming == "top" else (i_node_out < 0)
        ai = abs(i_e)
        hyst += p.coss_hyst_frac * dev.eoss(v)
        if hard:
            n_hard += 1
            ring += 0.5 * p.l_loop * ai * ai
            coss += q * v
            overlap += 0.5 * v * ai * t_on
            dead += (dev.vsd or 0.0) * ai * p.t_dead
        else:
            r = max(0.0, 1.0 - ai * p.t_dead / (2.0 * q)) if q > 0 else 0.0
            coss += q * v * r * r
            overlap += 0.5 * v * ai * t_off
            t_rc = max(0.0, p.t_dead - 2.0 * q / ai) if ai > 0 else 0.0
            dead += (dev.vsd or 0.0) * ai * t_rc
    L["coss"] = coss * fs
    L["overlap"] = overlap * fs
    L["dead_time"] = dead * fs
    L["coss_hysteresis"] = hyst * fs
    L["loop_ringing"] = ring * fs
    n_sw = 4 * (int(in_active) + int(out_active))
    L["gate"] = n_sw * dev.qg() * dev.vdrv * fs

    # --- core loss (iGSE on the piecewise-linear flux)
    mat = magnetics.MATERIALS[p.core]
    k = magnetics.steinmetz_k(mat)
    times = [s.t0 for s in w.segs] + [w.T]
    bflux = [p.k_b * (il + x) for x in w.knots]
    L["inductor_core"] = magnetics.igse_piecewise_linear(k, mat["alpha"], mat["beta"], times, bflux) * p.core_volume

    stage = sum(L.values())
    L["aux"] = p.p_aux_switching
    total = stage + L["aux"]

    # --- constraints
    ripple = w.ripple_pp()
    ipk = abs(il) + max(abs(min(w.knots)), abs(max(w.knots)))
    cf_rip = 0.0
    if in_active:
        cf_rip = max(cf_rip, pwm.cf_charge_pp(w, il, 1) / p.cfly_eff(vin / 2) / (vin / 2))
    if out_active:
        cf_rip = max(cf_rip, pwm.cf_charge_pp(w, il, 2) / p.cfly_eff(vout / 2) / (vout / 2))
    violations = []
    if not feasible:
        violations.append(reason or "duty infeasible")
    if ripple > p.max_ripple_pp:
        violations.append(f"ripple {ripple:.1f} A > {p.max_ripple_pp} A")
    if cf_rip > p.max_cfly_ripple:
        violations.append(f"flying-cap ripple {100*cf_rip:.1f}% > {100*p.max_cfly_ripple:.0f}%")
    if ipk > 0.7 * p.i_sat:
        violations.append(f"peak current {ipk:.1f} A > 70% Isat")
    return dict(
        vin=vin, vout=vout, pout=pout, fs=fs, mode=mode, phase=phase, d1=d1, d2=d2, il=il,
        iin=iin_dc, iout=iout, ripple_pp=ripple, i_peak=ipk, cfly_ripple=cf_rip, n_hard=n_hard,
        losses=L, loss_stage=stage, loss_total=total,
        eta_stage=pout / (pout + stage), eta=pout / (pout + total),
        feasible=not violations, violations=violations, label=mode_label(mode, d1, d2),
    )


def mode_label(mode: str, d1: float, d2: float) -> str:
    """Human label. Near D = 0.5 a three-level leg's node sits at Vbus/2 almost all the time:
    the inductor current barely ripples and the leg behaves as a soft-charged 2:1
    switched-capacitor stage (series-parallel), which is the converter's sweet spot."""
    if mode == "boost" and abs(d2 - 0.5) < 0.06:
        return "boost (SC 1:2 region)"
    if mode == "buck" and abs(d1 - 0.5) < 0.06:
        return "buck (SC 2:1 region)"
    return mode


def modes_for(vin: float, vout: float) -> List[str]:
    if vin > vout * 1.001:
        return ["buck", "buckboost"]
    if vin < vout * 0.999:
        return ["boost", "buckboost"]
    return ["buckboost"]


def best(vin: float, vout: float, pout: float, p: Optional[Params] = None) -> Dict:
    """Lowest total-loss feasible (mode, frequency) at an operating point."""
    p = p or Params()
    cands = []
    for mode in modes_for(vin, vout):
        for fs in p.f_candidates:
            r = evaluate(vin, vout, pout, fs, mode, p)
            cands.append(r)
    ok = [r for r in cands if r["feasible"]]
    pool = ok if ok else cands
    return min(pool, key=lambda r: r["loss_total"])


def bypass(v: float, pout: float, p: Optional[Params] = None) -> Dict:
    """Pass-through: panel tied to the battery through the two bidirectional GaN switches.
    No conversion and no MPPT (the panel sits at battery voltage)."""
    p = p or Params()
    bds = devices.get(p.bds)
    i = pout / v
    L = {"bds_path": 2 * bds.rds(p.tj) * i * i, "shunts": 2 * p.r_shunt * i * i,
         "pcb_copper": 0.5 * p.r_pcb * i * i}
    stage = sum(L.values())
    L["aux"] = p.p_aux_idle
    total = stage + L["aux"]
    return dict(vin=v, vout=v, pout=pout, mode="bypass", label="bypass", fs=0.0, losses=L,
                loss_stage=stage, loss_total=total, eta_stage=pout / (pout + stage), eta=pout / (pout + total),
                feasible=True, violations=[])


def efficiency_curve(vout: float, load_frac: float, vins, p: Optional[Params] = None) -> List[Dict]:
    p = p or Params()
    out = []
    for v in vins:
        out.append(best(v, vout, load_frac * p.spec.p_rated(v), p))
    return out
