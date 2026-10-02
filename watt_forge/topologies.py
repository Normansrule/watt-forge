"""Generic topology designer: size L and C and estimate a loss budget for the
classic two-level converters.

Supported: buck, boost, buck_boost (inverting), sepic, cuk, flyback,
four_switch (non-inverting four-switch buck-boost with buck / boost /
buck-boost mode selection). Each can be synchronous (sync=True, second switch
replaces the diode) or diode-rectified. The model is first-order and assumes
continuous conduction mode (CCM); the result reports when CCM is not met.

Honest limits: flyback leakage-inductance (clamp) loss is estimated with a
user leakage fraction; SEPIC/Cuk coupling capacitors are sized for ripple
but their ESR loss uses a simple pulsed-current RMS.
"""
from __future__ import annotations

import math
from typing import Dict

from . import devices, losses, magnetics, ratios

DEFAULTS = dict(
    topology="buck", vin=48.0, vout=12.0, pout=100.0, fs=200e3,
    ripple_frac=0.3, vripple_frac=0.01, device="EPC2302", sync=True,
    diode_vf=0.55, diode_qc_nc=30.0, dcr_mohm=4.0, esr_in_mohm=2.0, esr_out_mohm=2.0,
    tj=80.0, t_dead=15e-9, n=1.0, leakage_frac=0.02,
    core="ferrite_generic", b_design=0.30, energy_density=1.5e3,
)


def _merge(spec: dict) -> dict:
    s = dict(DEFAULTS)
    s.update({k: v for k, v in spec.items() if v is not None})
    return s


def _cell_losses(v_sw, i_valley, i_peak, d_main, i_sw, di, fs, dev, s, sync):
    """Loss of one two-level switching cell (main switch + sync switch or diode).

    v_sw: blocking voltage of the cell; i_sw: average cell current while conducting;
    di: peak-to-peak ripple; d_main: duty of the main switch.
    """
    out: Dict[str, float] = {}
    r = dev.rds(s["tj"])
    i2_main = d_main * (i_sw * i_sw + di * di / 12.0)
    i2_sec = (1 - d_main) * (i_sw * i_sw + di * di / 12.0)
    q = dev.qoss(v_sw)
    out["cond_switch"] = r * i2_main
    if sync:
        out["cond_switch"] += r * i2_sec
        if i_valley > 0:
            out["coss_hard"] = losses.hard_turn_on_halfbridge(q, v_sw, fs)
            out["overlap"] = 0.5 * v_sw * i_valley * dev.t_overlap(True) * fs
            t_rc_on = s["t_dead"]
        else:
            res = losses.zvs_residual_fraction(i_valley, s["t_dead"], q)
            out["coss_hard"] = q * v_sw * res * res * fs
            out["overlap"] = 0.0
            t_rc_on = max(0.0, s["t_dead"] - 2 * q / max(abs(i_valley), 1e-12))
        out["overlap"] += 0.5 * v_sw * abs(i_peak) * dev.t_overlap(False) * fs
        t_rc_off = max(0.0, s["t_dead"] - 2 * q / max(abs(i_peak), 1e-12))
        out["dead_time"] = (dev.vsd or 0) * (abs(i_valley) * t_rc_on + abs(i_peak) * t_rc_off) * fs
        out["reverse_recovery"] = losses.reverse_recovery(dev.qrr(), v_sw, fs) if i_valley > 0 else 0.0
        out["gate"] = 2 * losses.gate_drive(dev.qg(), dev.vdrv, fs)
    else:
        i_diode_avg = (1 - d_main) * i_sw
        out["cond_diode"] = s["diode_vf"] * i_diode_avg
        out["coss_hard"] = dev.eoss(v_sw) * fs + s["diode_qc_nc"] * 1e-9 * v_sw * fs
        out["overlap"] = 0.5 * v_sw * (max(i_valley, 0) * dev.t_overlap(True) + abs(i_peak) * dev.t_overlap(False)) * fs
        out["gate"] = losses.gate_drive(dev.qg(), dev.vdrv, fs)
    return out


def _add(a: Dict[str, float], b: Dict[str, float], scale: float = 1.0):
    for k, v in b.items():
        a[k] = a.get(k, 0.0) + v * scale


def design(**spec) -> dict:
    s = _merge(spec)
    top = s["topology"]
    vin, vout, pout, fs = float(s["vin"]), abs(float(s["vout"])), float(s["pout"]), float(s["fs"])
    dev = devices.get(s["device"])
    sync = bool(s["sync"])
    iout = pout / vout
    m = vout / vin
    mat = magnetics.MATERIALS[s["core"]]
    kst = magnetics.steinmetz_k(mat)
    # --- efficiency guess, iterate for the input current
    eta = 0.95
    result = None
    for _ in range(3):
        notes = []
        pin = pout / eta
        iin = pin / vin
        lb: Dict[str, float] = {}
        inductors = []
        if top == "buck":
            il = iout
            d = min((vout + il * (dev.rds(s["tj"]) + s["dcr_mohm"] * 1e-3)) / vin, 0.995)
            v_sw = vin
            di = s["ripple_frac"] * il
            l = ratios.inductor_for_ripple("buck", vin, vout, d, di, fs)
            _add(lb, _cell_losses(v_sw, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync))
            inductors.append((l, il, di, d))
            c_out = ratios.output_cap_for_ripple("buck", iout, d, di, s["vripple_frac"] * vout, fs)
            i_cin_rms = math.sqrt(max(d * (il**2 + di**2 / 12) - (d * il) ** 2, 0))
            i_cout_rms = di / math.sqrt(12)
        elif top in ("boost", "buck_boost", "sepic", "cuk", "flyback"):
            n = float(s["n"]) if top == "flyback" else 1.0
            if top == "boost":
                d = 1 - (vin - iin * (dev.rds(s["tj"]) + s["dcr_mohm"] * 1e-3)) / vout
                il = iin
                v_sw = vout
                i_sw = il
            elif top == "flyback":
                d = (vout / n) / (vin + vout / n)
                il = iin / d            # primary-referred magnetizing current while on
                v_sw = vin + vout / n
                i_sw = il
            else:
                d = vout / (vin + vout)
                il = iout / (1 - d)     # buck-boost inductor / SEPIC & Cuk switch current
                v_sw = vin + vout
                i_sw = il if top == "buck_boost" else iin + iout
            d = min(max(d, 0.001), 0.995)
            if top in ("sepic", "cuk"):
                di1 = s["ripple_frac"] * iin
                di2 = s["ripple_frac"] * iout
                l1 = vin * d / (di1 * fs)
                l2 = vin * d / (di2 * fs)
                inductors += [(l1, iin, di1, d), (l2, iout, di2, d)]
                di = di1 + di2
            else:
                di = s["ripple_frac"] * il
                l = vin * d / (di * fs)
                inductors.append((l, il, di, d))
            _add(lb, _cell_losses(v_sw, i_sw - di / 2, i_sw + di / 2, d, i_sw, di, fs, dev, s, sync))
            c_out = ratios.output_cap_for_ripple("boost", iout, d, di, s["vripple_frac"] * vout, fs)
            i_cout_rms = math.sqrt(max(d * iout**2 + (1 - d) * ((i_sw - iout) ** 2), 0)) if top != "cuk" else di / math.sqrt(12)
            i_cin_rms = di / math.sqrt(12) if top in ("boost", "sepic", "cuk") else math.sqrt(max(d * il**2 - (d * il) ** 2, 0))
            if top == "flyback":
                ipk = il + di / 2
                l_lk = s["leakage_frac"] * inductors[0][0]
                lb["leakage_clamp"] = 0.5 * l_lk * ipk * ipk * fs
                notes.append("Flyback leakage (clamp) loss uses leakage_frac of Lm; transformer winding AC loss not modelled.")
        elif top == "four_switch":
            r = dev.rds(s["tj"])
            if m < 0.95:
                mode = "buck"
                il = iout
                d = min((vout + il * (2 * r + s["dcr_mohm"] * 1e-3)) / vin, 0.995)
                di = s["ripple_frac"] * il
                l = ratios.inductor_for_ripple("buck", vin, vout, d, di, fs)
                _add(lb, _cell_losses(vin, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync))
                lb["cond_switch"] += r * (il * il + di * di / 12)  # boost-leg top switch always on
                i_cin_rms = math.sqrt(max(d * (il**2 + di**2 / 12) - (d * il) ** 2, 0))
                i_cout_rms = di / math.sqrt(12)
            elif m > 1.05:
                mode = "boost"
                il = iin
                d = 1 - (vin - il * (2 * r + s["dcr_mohm"] * 1e-3)) / vout
                di = s["ripple_frac"] * il
                l = vin * d / (di * fs)
                _add(lb, _cell_losses(vout, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync))
                lb["cond_switch"] += r * (il * il + di * di / 12)  # buck-leg top switch always on
                i_cin_rms = di / math.sqrt(12)
                i_cout_rms = math.sqrt(max(d * iout**2 + (1 - d) * (il - iout) ** 2, 0))
            else:
                mode = "buck-boost"
                d = m / (1 + m)
                il = iout / (1 - d)
                di = s["ripple_frac"] * il
                l = vin * d / (di * fs)
                _add(lb, _cell_losses(vin, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync))
                _add(lb, _cell_losses(vout, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync))
                i_cin_rms = math.sqrt(max(d * il**2 - (d * il) ** 2, 0))
                i_cout_rms = math.sqrt(max(d * iout**2 + (1 - d) * (il - iout) ** 2, 0))
            notes.append(f"four-switch operating in {mode} mode")
            inductors.append((l, il, di, d))
            c_out = ratios.output_cap_for_ripple("buck" if mode == "buck" else "boost", iout, d, di, s["vripple_frac"] * vout, fs)
            v_sw = max(vin, vout)
        else:
            raise ValueError(f"unknown topology {top!r}")

        # inductor(s): copper + core (iGSE, triangular flux)
        lb["inductor_dcr"] = 0.0
        lb["inductor_core"] = 0.0
        for (lx, ilx, dix, dx) in inductors:
            lb["inductor_dcr"] += s["dcr_mohm"] * 1e-3 * (ilx * ilx + dix * dix / 12)
            ipk = abs(ilx) + dix / 2
            vol = lx * ipk * ipk / (2 * s["energy_density"])
            dbpp = s["b_design"] * dix / max(ipk, 1e-9)
            pv = magnetics.igse_triangular(kst, mat["alpha"], mat["beta"], fs, dbpp, dx)
            lb["inductor_core"] += pv * vol
        lb["cap_esr"] = s["esr_in_mohm"] * 1e-3 * i_cin_rms**2 + s["esr_out_mohm"] * 1e-3 * i_cout_rms**2
        total = sum(lb.values())
        eta = pout / (pout + total)
        l_main = inductors[0][0]
        k = ratios.k_param(l_main, vout * vout / pout, fs)
        valley = inductors[0][1] - inductors[0][2] / 2
        ccm = valley > 0
        if not ccm and sync:
            notes.append("Valley current is negative: forced CCM (synchronous rectifier conducts backwards; helps ZVS).")
        elif not ccm:
            notes.append("Valley current below zero: a diode converter would enter DCM; this CCM estimate is not valid.")
        result = dict(
            topology=top, sync=sync, device=dev.id, d=d, m=m, fs=fs, vin=vin, vout=vout, pout=pout,
            iin=pout / eta / vin, iout=iout, il=inductors[0][1], delta_i=inductors[0][2],
            l=l_main, l2=inductors[1][0] if len(inductors) > 1 else None, c_out=c_out,
            v_switch=v_sw, losses=lb, total_loss=total, eta=eta, k=k,
            ccm=ccm, notes=notes,
        )
    return result


def compare_devices(device_ids, **spec) -> Dict[str, dict]:
    return {d: design(**{**spec, "device": d}) for d in device_ids}
