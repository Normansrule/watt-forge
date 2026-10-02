"""Primitive loss equations. Each returns watts.

These are the textbook building blocks (Erickson & Maksimovic 3rd ed.,
DOI 10.1007/978-3-030-43881-4). The flagship model in
``watt_forge.flagship.model`` combines them edge by edge.
"""
from __future__ import annotations


def conduction(i_rms: float, r: float) -> float:
    """I_rms^2 * R  (switch Rds(on), inductor DCR, capacitor ESR, shunts, copper)."""
    return i_rms * i_rms * r


def rms_trapezoid(i_avg: float, delta_i: float, duty: float) -> float:
    """RMS of a current that equals a triangular-ripple current (mean i_avg,
    peak-to-peak delta_i) for a fraction `duty` of the period and zero otherwise.

    I_rms^2 = D * (I^2 + dI^2/12)
    """
    return (duty * (i_avg * i_avg + delta_i * delta_i / 12.0)) ** 0.5


def rms_triangle_ac(delta_i: float) -> float:
    """RMS of the AC part of a triangular ripple with peak-to-peak delta_i."""
    return delta_i / (12.0 ** 0.5)


def overlap(v: float, i: float, t_on: float, t_off: float, fs: float) -> float:
    """Voltage-current overlap loss of a hard-switched transition pair:
    P = 1/2 * V * I * (t_on + t_off) * fs."""
    return 0.5 * v * abs(i) * (t_on + t_off) * fs


def coss_linear(c_oss: float, v: float, fs: float) -> float:
    """Energy in one device's (linear) output capacitance dumped per turn-on:
    P = 1/2 * Coss * V^2 * fs."""
    return 0.5 * c_oss * v * v * fs


def qoss_at(qoss_ref: float, v_ref: float, v: float, m: float) -> float:
    """Output charge at voltage v assuming Qoss(V) = Qoss_ref * (V/V_ref)^m.

    m = 1 is a linear capacitor; m = 0.5 is an abrupt junction; GaN fits ~0.6-0.67.
    """
    if v <= 0:
        return 0.0
    return qoss_ref * (v / v_ref) ** m


def eoss_from_qoss(q: float, v: float, m: float) -> float:
    """Energy stored in Coss for the power law Q = k V^m:
    E = integral(v dQ) = m/(m+1) * Q * V.  (m=1 gives the familiar 1/2 C V^2.)"""
    return m / (m + 1.0) * q * v


def hard_turn_on_halfbridge(qoss: float, v: float, fs: float) -> float:
    """Hard turn-on loss in a half-bridge of two identical devices, per transition
    per period: P = Qoss(V) * V * fs.

    The turning-on device dumps its own Eoss and also dissipates (Qoss*V - Eoss)
    while charging the opposite device's Coss from the bus. For a linear
    capacitor that is C V^2 = 2 x (1/2 C V^2).
    """
    return qoss * v * fs


def reverse_recovery(qrr: float, v: float, fs: float) -> float:
    """Diode reverse-recovery loss, first order: P = Qrr * V * fs. GaN HEMTs: Qrr = 0."""
    return qrr * v * fs


def gate_drive(qg: float, v_drv: float, fs: float) -> float:
    """Gate charge energy per switching period: P = Qg * Vdrv * fs (lost in driver + Rg)."""
    return qg * v_drv * fs


def dead_time(v_sd: float, i: float, t_dead: float, fs: float, n_per_period: int = 2) -> float:
    """Reverse (body-diode or GaN third-quadrant) conduction during dead time:
    P = Vsd * |I| * t_dead * fs * n."""
    return v_sd * abs(i) * t_dead * fs * n_per_period


def zvs_residual_fraction(i: float, t_dead: float, qoss: float) -> float:
    """Fraction of the node swing NOT completed by current |i| within the dead time.

    A transition needs charge 2*Qoss (one device discharges, the other charges).
    Returns 0 for full zero-voltage switching (ZVS), 1 for fully hard switching.
    """
    if qoss <= 0:
        return 0.0
    x = abs(i) * t_dead / (2.0 * qoss)
    return max(0.0, 1.0 - x)


def overlap_time(q_sw: float, v_drv: float, v_pl: float, r_g: float, turn_on: bool = True) -> float:
    """Estimate the current-voltage overlap time from the switching charge.

    turn-on:  Ig = (Vdrv - Vpl)/Rg ; turn-off: Ig = Vpl/Rg ; t = Qsw / Ig.
    q_sw is usually taken as ~1.5 * Qgd (Qgs2 + Qgd).
    """
    ig = (v_drv - v_pl) / r_g if turn_on else v_pl / r_g
    return q_sw / ig
