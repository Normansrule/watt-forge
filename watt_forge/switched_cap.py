"""Switched-capacitor (SC) converter loss: slow- and fast-switching limits.

Seeman & Sanders, "Analysis and Optimization of Switched-Capacitor DC-DC
Converters", IEEE TPEL 23(2), 2008, DOI 10.1109/TPEL.2007.915182.

An SC converter behaves like an ideal transformer of ratio n followed by an
output resistance R_out. The loss is intrinsic: every time a capacitor is
connected to a different voltage, charge redistributes through a resistance
and dissipates energy regardless of how small that resistance is.

    R_SSL = sum_i (a_c,i)^2 / (C_i f)        slow-switching limit (caps fully settle)
    R_FSL = 2 * sum_i R_i (a_r,i)^2          fast-switching limit (currents ~constant; 50% duty)
    R_out ~ sqrt(R_SSL^2 + R_FSL^2)          smooth approximation between the limits

a_c, a_r are charge multipliers: charge through each capacitor / switch per
period, normalised to the output charge per period.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

# 2:1 series-parallel: one flying cap carries q_out/2 in each phase; four switches each carry q_out/2.
SERIES_PARALLEL_2TO1 = {"ratio": 0.5, "a_c": [0.5], "a_r": [0.5, 0.5, 0.5, 0.5]}


def r_ssl(a_c: Sequence[float], caps: Sequence[float], f: float) -> float:
    return sum(a * a / (c * f) for a, c in zip(a_c, caps))


def r_fsl(a_r: Sequence[float], rs: Sequence[float]) -> float:
    return 2.0 * sum(r * a * a for a, r in zip(a_r, rs))


def r_out(a_c, caps, f, a_r, rs) -> float:
    s = r_ssl(a_c, caps, f)
    q = r_fsl(a_r, rs)
    return math.hypot(s, q)


def sc_loss(i_out: float, rout: float) -> float:
    return i_out * i_out * rout


def sc_efficiency(v_in: float, ratio: float, i_out: float, rout: float) -> float:
    """Efficiency of an SC stage with ideal ratio `ratio` and output resistance rout,
    counting only the intrinsic (charge-redistribution + conduction) loss:
    eta = Vout / (ratio * Vin) with Vout = ratio*Vin - Iout*Rout."""
    v_out = ratio * v_in - i_out * rout
    return v_out / (ratio * v_in)


def simulate_series_parallel(v_in: float, v_out: float, c: float, r_sw: float, f: float) -> dict:
    """Exact periodic steady state of a 2:1 series-parallel SC converter into an
    ideal voltage sink v_out (a battery), 50% duty, four switches of resistance r_sw.

    Phase 1 (T/2): Vin -> S1 -> C -> S2 -> Vout, loop resistance 2 r_sw, C charges toward Vin - Vout.
    Phase 2 (T/2): C -> S3 -> Vout -> S4, loop resistance 2 r_sw, C discharges toward Vout.
    Returns average output current, the implied R_out = (Vin/2 - Vout)/Iout and the loss.
    """
    T = 1.0 / f
    tau = 2.0 * r_sw * c
    a = math.exp(-(T / 2.0) / tau)
    t1 = v_in - v_out  # target voltage for C in phase 1
    t2 = v_out         # target voltage for C in phase 2
    # v after phase1: v1 = t1 + (v0 - t1) a ; after phase 2: v0 = t2 + (v1 - t2) a (periodic)
    # => v0 = t2 + (t1 + (v0 - t1) a - t2) a  => v0 (1 - a^2) = t2 (1 - a) + t1 a (1 - a)
    v0 = (t2 * (1 - a) + t1 * a * (1 - a)) / (1 - a * a)
    v1 = t1 + (v0 - t1) * a
    q1 = c * (v1 - v0)          # charge delivered through Vout in phase 1 (C charging, series with output)
    q2 = c * (v1 - v0)          # charge delivered in phase 2 (C discharging into output)
    i_out = (q1 + q2) / T
    # energy dissipated: input energy - output energy
    e_in = v_in * q1
    e_out = v_out * (q1 + q2)
    p_loss = (e_in - e_out) / T
    rout = (v_in / 2.0 - v_out) / i_out if i_out != 0 else float("inf")
    return {"i_out": i_out, "r_out": rout, "p_loss": p_loss, "v_c_min": v0, "v_c_max": v1}


def simulate_series_parallel_numeric(v_in, v_out, c, r_sw, f, steps_per_phase=4000, periods=200):
    """Brute-force forward-Euler check of the exact solution above (used only in tests)."""
    T = 1.0 / f
    dt = (T / 2) / steps_per_phase
    v = v_out
    q_out = 0.0
    e_in = 0.0
    for p in range(periods):
        last = p == periods - 1
        for _ in range(steps_per_phase):
            i = (v_in - v - v_out) / (2 * r_sw)
            v += i / c * dt
            if last:
                q_out += i * dt
                e_in += v_in * i * dt
        for _ in range(steps_per_phase):
            i = (v - v_out) / (2 * r_sw)
            v -= i / c * dt
            if last:
                q_out += i * dt
    i_avg = q_out / T
    return {"i_out": i_avg, "r_out": (v_in / 2 - v_out) / i_avg, "p_loss": (e_in - v_out * q_out) / T}


def rout_curve(c: float, r_sw: float, freqs: np.ndarray) -> dict:
    """R_out vs frequency for the 2:1 series-parallel (for the lesson plot)."""
    ssl = np.array([r_ssl([0.5], [c], f) for f in freqs])
    fsl = np.full_like(ssl, r_fsl([0.5] * 4, [r_sw] * 4))
    return {"f": freqs, "ssl": ssl, "fsl": fsl, "approx": np.hypot(ssl, fsl)}
