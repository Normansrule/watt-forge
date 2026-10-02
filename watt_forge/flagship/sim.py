"""Time-domain circuit simulation of the flagship converter (piecewise-linear, exact per interval).

What is simulated physically (from circuit equations):
  * inductor current and both flying-capacitor voltages (they are NOT assumed balanced),
  * every switch's on-resistance, inductor DCR, flying-capacitor ESR, loop copper,
  * dead time, with third-quadrant (reverse) conduction of the GaN device at V_SD,
  * the exact periodic steady state (solved directly from the one-period state map,
    no start-up transient to wait out).
What is added per event (as a circuit simulator with loss tables such as PLECS does):
  * Coss (hard turn-on) energy, voltage-current overlap, Coss hysteresis, loop ringing,
    gate charge, inductor core loss (iGSE on the simulated current), input/output capacitor
    ESR, DC shunts, the bidirectional-switch disconnect and housekeeping power.

The simulator solves its own duty cycle so the delivered power hits the target,
then reports efficiency. tests/test_flagship_sim.py checks it against the analytic
model; hardware/flagship/spice/ cross-checks the circuit part against ngspice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.linalg import expm

from .. import devices, magnetics
from . import model as fmodel
from .params import Params

TOP, BOT, DEAD = 1, 0, 2


@dataclass
class Pair:
    leg: str       # "in" or "out"
    name: str      # "outer" / "inner"
    t_top: float   # time the TOP switch is commanded on
    t_bot: float   # time the BOTTOM switch is commanded on


def _pairs(mode: str, d1: float, d2: float, phase: float, T: float) -> List[Pair]:
    ps: List[Pair] = []
    if mode in ("buck", "buckboost"):
        ps.append(Pair("in", "outer", 0.0, (d1 * T) % T))
        ps.append(Pair("in", "inner", T / 2, (T / 2 + d1 * T) % T))
    if mode in ("boost", "buckboost"):
        ps.append(Pair("out", "outer", (phase * T + d2 * T) % T, (phase * T) % T))
        ps.append(Pair("out", "inner", (phase * T + T / 2 + d2 * T) % T, (phase * T + T / 2) % T))
    return ps


def _pair_state(pr: Pair, t: float, T: float, td: float) -> int:
    def since(t0):
        return (t - t0) % T
    s_top, s_bot = since(pr.t_top), since(pr.t_bot)
    last_is_top = s_top < s_bot
    if last_is_top:
        return DEAD if s_top < td else TOP
    return DEAD if s_bot < td else BOT


def _timeline(pairs: List[Pair], T: float, td: float):
    pts = {0.0, T}
    for pr in pairs:
        for t0 in (pr.t_top, pr.t_bot):
            pts.add(t0 % T)
            pts.add((t0 + td) % T)
    ts = sorted(pts)
    uniq = [ts[0]]
    for t in ts[1:]:
        if t - uniq[-1] > 1e-13:
            uniq.append(t)
    uniq[-1] = T
    segs = []
    for t0, t1 in zip(uniq, uniq[1:]):
        tm = 0.5 * (t0 + t1)
        segs.append((t0, t1 - t0, [_pair_state(pr, tm, T, td) for pr in pairs]))
    return segs


class Circuit:
    def __init__(self, vin, vout, mode, p: Params, vsd: float, r_sw: float):
        self.vin, self.vout, self.mode, self.p = vin, vout, mode, p
        self.vsd, self.r_sw = vsd, r_sw
        self.in_active = mode in ("buck", "buckboost")
        self.out_active = mode in ("boost", "buckboost")
        self.c1 = p.cfly_eff(vin / 2)
        self.c2 = p.cfly_eff(vout / 2)
        self.esr = p.cfly_esr()
        self.dcr = fmodel._dcr_hot(p)
        # state indices: 0 = iL, then active flying caps
        self.idx = {"i": 0}
        k = 1
        if self.in_active:
            self.idx["v1"] = k
            k += 1
        if self.out_active:
            self.idx["v2"] = k
            k += 1
        self.n = k

    def effective(self, pairs: List[Pair], states: List[int], sign: float):
        """Resolve dead-time states to conducting switches by current direction.
        Returns (a, b, c, d, v_extra) where v_extra is the net Vsd term in the loop (vA - vB)."""
        a = b = c = d = 1
        v_extra = 0.0
        for pr, st in zip(pairs, states):
            if st == DEAD:
                if pr.leg == "in":
                    top_on = sign < 0          # current into node A -> pushed up -> top reverse-conducts
                    v_extra += -self.vsd * sign
                else:
                    top_on = sign > 0          # current into node B -> pushed up -> top reverse-conducts
                    v_extra -= self.vsd * sign
            else:
                top_on = st == TOP
            bit = 1 if top_on else 0
            if pr.leg == "in":
                if pr.name == "outer":
                    a = bit
                else:
                    b = bit
            else:
                if pr.name == "outer":
                    c = bit
                else:
                    d = bit
        return a, b, c, d, v_extra

    def system(self, a, b, c, d, v_extra):
        n = self.n
        A = np.zeros((n, n))
        bb = np.zeros(n)
        L = self.p.l
        r = 4 * self.r_sw + self.dcr + self.p.r_pcb
        cf1 = self.in_active and a != b
        cf2 = self.out_active and c != d
        if cf1:
            r += self.esr
        if cf2:
            r += self.esr
        A[0, 0] = -r / L
        const = (self.vin if a else 0.0) - (self.vout if c else 0.0) + v_extra
        if self.in_active:
            k = self.idx["v1"]
            if (a, b) == (1, 0):
                A[0, k] = -1.0 / L
                A[k, 0] = 1.0 / self.c1
            elif (a, b) == (0, 1):
                A[0, k] = 1.0 / L
                A[k, 0] = -1.0 / self.c1
        if self.out_active:
            k = self.idx["v2"]
            if (c, d) == (1, 0):
                A[0, k] = 1.0 / L
                A[k, 0] = -1.0 / self.c2
            elif (c, d) == (0, 1):
                A[0, k] = -1.0 / L
                A[k, 0] = 1.0 / self.c2
        bb[0] = const / L
        return A, bb, r, cf1, cf2


def _aug(A, b, tau):
    n = A.shape[0]
    M = np.zeros((n + 1, n + 1))
    M[:n, :n] = A
    M[:n, n] = b
    return expm(M * tau)


def run_period(vin, vout, mode, d1, d2, phase, fs, p: Params, td: float, signs=None, n_sub: int = 48):
    """Solve the periodic steady state for fixed duties; return waveform + integrals."""
    dev = devices.get(p.switch)
    r_sw = fmodel._r_sw(p)
    ckt = Circuit(vin, vout, mode, p, dev.vsd or 0.0, r_sw)
    T = 1.0 / fs
    pairs = _pairs(mode, d1, d2, phase, T)
    segs = _timeline(pairs, T, td)
    if signs is None:
        signs = [1.0] * len(segs)
    mats = []
    eff = []
    for (t0, tau, st), sg in zip(segs, signs):
        a, b, c, d, vx = ckt.effective(pairs, st, sg if any(s == DEAD for s in st) else 1.0)
        A, bb, r, cf1, cf2 = ckt.system(a, b, c, d, vx)
        mats.append((A, bb, tau))
        eff.append((a, b, c, d, vx, r))
    n = ckt.n
    Phi = np.eye(n + 1)
    for A, bb, tau in mats:
        Phi = _aug(A, bb, tau) @ Phi
    x0 = np.linalg.solve(np.eye(n) - Phi[:n, :n], Phi[:n, n])
    # march with sub-steps, accumulate integrals (trapezoid)
    x = np.concatenate([x0, [1.0]])
    tt, ii = [0.0], [x0[0]]
    E_in = E_out = I2 = Iin = Iin2 = Iout = Iout2 = Ecf = Evsd = Eres = 0.0
    seg_start_i = []
    t = 0.0
    for (A, bb, tau), (a, b, c, d, vx, r) in zip(mats, eff):
        seg_start_i.append(x[0])
        h = tau / n_sub
        step = _aug(A, bb, h)
        for _ in range(n_sub):
            i0 = x[0]
            x = step @ x
            i1 = x[0]
            t += h
            sq = h * (i0 * i0 + i0 * i1 + i1 * i1) / 3.0   # exact for linear segments
            lin = h * (i0 + i1) / 2.0
            I2 += sq
            Eres += r * sq
            if a:
                E_in += vin * lin
                Iin += lin
                Iin2 += sq
            if c:
                E_out += vout * lin
                Iout += lin
                Iout2 += sq
            if vx != 0.0:
                Evsd += -vx * lin   # power into the Vsd drops (vx carries the sign)
            tt.append(t)
            ii.append(i1)
    close = abs(x[0] - x0[0])
    return dict(T=T, pairs=pairs, segs=segs, eff=eff, x0=x0, t=np.array(tt), i=np.array(ii),
                E_in=E_in, E_out=E_out, I2=I2 / T, Iin=Iin / T, Iin2=Iin2 / T, Iout=Iout / T,
                Iout2=Iout2 / T, P_res=Eres / T, P_vsd=Evsd / T, seg_start_i=seg_start_i, closure=close,
                ckt=ckt)


def _signs_from(res, segs_len) -> List[float]:
    return [1.0 if v >= 0 else -1.0 for v in res["seg_start_i"]][:segs_len]


def solve_steady(vin, vout, mode, d1, d2, phase, fs, p, td):
    res = run_period(vin, vout, mode, d1, d2, phase, fs, p, td)
    for _ in range(4):
        sg = _signs_from(res, len(res["segs"]))
        res2 = run_period(vin, vout, mode, d1, d2, phase, fs, p, td, sg)
        if _signs_from(res2, len(res2["segs"])) == sg:
            return res2
        res = res2
    return res


def simulate(vin: float, vout: float, pout: float, fs: float, mode: str, p: Optional[Params] = None,
             phase: Optional[float] = None, td: Optional[float] = None, events: bool = True) -> Dict:
    """Simulate one operating point; returns efficiency and a loss breakdown."""
    p = p or Params()
    ana = fmodel.evaluate(vin, vout, pout, fs, mode, p, phase)
    phase = ana["phase"]
    td = p.t_dead if td is None else td
    d1, d2 = ana["d1"], ana["d2"]

    def pout_of(x):
        if mode == "buck":
            r = solve_steady(vin, vout, mode, x, 0.0, phase, fs, p, td)
        else:
            r = solve_steady(vin, vout, mode, d1, x, phase, fs, p, td)
        return vout * r["Iout"], r

    x0 = d1 if mode == "buck" else d2
    xmin, xmax = 2.0 * td * fs + 1e-4, 1.0 - 2.0 * td * fs - 1e-4
    lo, hi = max(xmin, x0 - 0.02), min(xmax, x0 + 0.02)
    plo, _ = pout_of(lo)
    phi, _ = pout_of(hi)
    for _ in range(20):
        if (plo - pout) * (phi - pout) <= 0:
            break
        lo, hi = max(xmin, lo - 0.02), min(xmax, hi + 0.02)
        plo, _ = pout_of(lo)
        phi, _ = pout_of(hi)
    else:
        raise RuntimeError("could not bracket the duty cycle")
    # Illinois (modified regula falsi)
    side = 0
    x, res = x0, None
    for _ in range(80):
        x = hi - (phi - pout) * (hi - lo) / (phi - plo)
        px, res = pout_of(x)
        if abs(px - pout) < 1e-7 * max(pout, 1.0):
            break
        if (px - pout) * (phi - pout) > 0:
            hi, phi = x, px
            if side == -1:
                plo = pout + (plo - pout) / 2
            side = -1
        else:
            lo, plo = x, px
            if side == 1:
                phi = pout + (phi - pout) / 2
            side = 1
    if mode == "buck":
        d1 = x
    else:
        d2 = x
    dev = devices.get(p.switch)
    bds = devices.get(p.bds)
    P_out = vout * res["Iout"]
    P_in_ckt = res["E_in"] / res["T"]
    L: Dict[str, float] = {}
    L["circuit_resistive"] = res["P_res"]
    L["dead_time_conduction"] = res["P_vsd"]
    if events:
        # event losses at each command edge using the simulated current
        T = res["T"]
        t = res["t"]
        iw = res["i"]
        coss = overlap = hyst = ring = 0.0
        t_on, t_off = dev.t_overlap(True), dev.t_overlap(False)
        for pr in res["pairs"]:
            for t_cmd, incoming in ((pr.t_top, "top"), (pr.t_bot, "bottom")):
                i_e = float(np.interp(t_cmd % T, t, iw))
                v = (vin if pr.leg == "in" else vout) / 2.0
                q = dev.qoss(v)
                i_node_out = i_e if pr.leg == "in" else -i_e
                hard = (i_node_out > 0) if incoming == "top" else (i_node_out < 0)
                ai = abs(i_e)
                hyst += p.coss_hyst_frac * dev.eoss(v)
                if hard:
                    coss += q * v
                    overlap += 0.5 * v * ai * t_on
                    ring += 0.5 * p.l_loop * ai * ai
                else:
                    rr = max(0.0, 1.0 - ai * td / (2.0 * q)) if q > 0 else 0.0
                    coss += q * v * rr * rr
                    overlap += 0.5 * v * ai * t_off
        L["coss"] = coss * fs
        L["overlap"] = overlap * fs
        L["coss_hysteresis"] = hyst * fs
        L["loop_ringing"] = ring * fs
        n_sw = 4 * (int(mode in ("buck", "buckboost")) + int(mode in ("boost", "buckboost")))
        L["gate"] = n_sw * dev.qg() * dev.vdrv * fs
        mat = magnetics.MATERIALS[p.core]
        k = magnetics.steinmetz_k(mat)
        # decimate to segment knots is not enough here (curvature); use all samples
        L["inductor_core"] = magnetics.igse_piecewise_linear(k, mat["alpha"], mat["beta"], list(t), list(p.k_b * iw)) * p.core_volume
        dcr = fmodel._dcr_hot(p)
        il = float(np.trapezoid(iw, t) / T)
        L["inductor_ac"] = dcr * (p.rac_factor - 1.0) * max(res["I2"] - il * il, 0.0)
        L["cin_cout_esr"] = p.esr_in * max(res["Iin2"] - res["Iin"] ** 2, 0.0) + p.esr_out * max(res["Iout2"] - res["Iout"] ** 2, 0.0)
        L["shunts"] = p.r_shunt * (res["Iin"] ** 2 + res["Iout"] ** 2)
        L["bds_disconnect"] = bds.rds(p.tj) * res["Iin"] ** 2
        L["aux"] = p.p_aux_switching
    extra = sum(v for k2, v in L.items() if k2 not in ("circuit_resistive", "dead_time_conduction"))
    P_in = P_in_ckt + extra
    aux = L.get("aux", 0.0)
    return dict(vin=vin, vout=vout, pout=P_out, fs=fs, mode=mode, d1=d1, d2=d2, phase=phase,
                eta=P_out / P_in, eta_stage=P_out / (P_in - aux), losses=L, loss_total=P_in - P_out,
                energy_residual=(P_in_ckt - P_out - res["P_res"] - res["P_vsd"]),
                closure=res["closure"], t=res["t"], i=res["i"], x0=res["x0"], res=res)


def ideal_switch_efficiency(vin, vout, pout, fs, mode, p=None, phase=None):
    """Conduction-only efficiency with zero dead time (for the ngspice cross-check)."""
    return simulate(vin, vout, pout, fs, mode, p, phase, td=0.0, events=False)
