"""Conversion ratios, balance laws, conduction-mode boundaries and component sizing.

Conventions (SI units throughout):
    D   duty cycle of the main (controlled) switch, 0..1
    M   conversion ratio Vout/Vin
    fs  switching frequency [Hz], Ts = 1/fs
    R   load resistance [ohm]
    K   = 2 L / (R Ts), the dimensionless DCM parameter (Erickson & Maksimovic, ch. 5)
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

# ---------------------------------------------------------------- ideal ratios

def m_buck(d: float) -> float:
    """Ideal CCM buck: M = D."""
    return d


def m_boost(d: float) -> float:
    """Ideal CCM boost: M = 1/(1-D)."""
    return 1.0 / (1.0 - d)


def m_buck_boost(d: float) -> float:
    """Ideal CCM inverting buck-boost: M = -D/(1-D)."""
    return -d / (1.0 - d)


def m_sepic(d: float) -> float:
    """Ideal CCM SEPIC (non-inverting): M = D/(1-D)."""
    return d / (1.0 - d)


def m_cuk(d: float) -> float:
    """Ideal CCM Cuk (inverting): M = -D/(1-D)."""
    return -d / (1.0 - d)


def m_flyback(d: float, n: float) -> float:
    """Ideal CCM flyback with turns ratio n = Ns/Np: M = n D/(1-D)."""
    return n * d / (1.0 - d)


def m_four_switch(d_buck: float, d_boost: float) -> float:
    """Ideal non-inverting four-switch buck-boost: M = D1/(1-D2)."""
    return d_buck / (1.0 - d_boost)


IDEAL_RATIO = {
    "buck": m_buck,
    "boost": m_boost,
    "buck_boost": m_buck_boost,
    "sepic": m_sepic,
    "cuk": m_cuk,
}


def duty_for_ratio(topology: str, m: float, n: float = 1.0) -> float:
    """Invert the ideal CCM ratio. |m| is used for the inverting topologies."""
    a = abs(m)
    if topology in ("buck", "sync_buck"):
        return a
    if topology in ("boost", "sync_boost"):
        return 1.0 - 1.0 / a
    if topology in ("buck_boost", "sync_buck_boost", "sepic", "cuk"):
        return a / (1.0 + a)
    if topology == "flyback":
        return a / (n + a)
    raise ValueError(f"unknown topology {topology!r}")


# ------------------------------------------------------ ratios with resistance

def m_buck_lossy(d: float, r_load: float, r_on: float, r_l: float) -> float:
    """Synchronous buck with switch resistance r_on and inductor DCR r_l.

    Volt-second balance with drops: D*Vin - V - I*(r_on + r_l) = 0, I = V/R
    =>  M = D / (1 + (r_on + r_l)/R)
    """
    return d / (1.0 + (r_on + r_l) / r_load)


def m_boost_lossy(d: float, r_load: float, r_on: float, r_l: float) -> float:
    """Synchronous boost: M = 1/(1-D) * 1/(1 + (r_on + r_l)/((1-D)^2 R))."""
    dp = 1.0 - d
    return (1.0 / dp) / (1.0 + (r_on + r_l) / (dp * dp * r_load))


def m_buck_boost_lossy(d: float, r_load: float, r_on: float, r_l: float) -> float:
    """Synchronous inverting buck-boost (magnitude):
    |M| = D/(1-D) * 1/(1 + (r_on + r_l)/((1-D)^2 R))."""
    dp = 1.0 - d
    return (d / dp) / (1.0 + (r_on + r_l) / (dp * dp * r_load))


# --------------------------------------------------------------- balance laws

def average_over_period(values: Sequence[float], durations: Sequence[float]) -> float:
    """Time-average of a piecewise-constant waveform."""
    total = float(sum(durations))
    if total <= 0:
        raise ValueError("durations must sum to a positive period")
    return sum(v * t for v, t in zip(values, durations)) / total


def volt_second_residual(v_l: Sequence[float], durations: Sequence[float]) -> float:
    """Average inductor voltage over one period. Zero in periodic steady state."""
    return average_over_period(v_l, durations)


def charge_residual(i_c: Sequence[float], durations: Sequence[float]) -> float:
    """Average capacitor current over one period. Zero in periodic steady state."""
    return average_over_period(i_c, durations)


# ---------------------------------------------------------- CCM / DCM boundary

def k_param(l: float, r_load: float, fs: float) -> float:
    return 2.0 * l * fs / r_load


def k_crit(topology: str, d: float) -> float:
    """K_crit(D): the converter is in CCM when K > K_crit."""
    if topology == "buck":
        return 1.0 - d
    if topology == "boost":
        return d * (1.0 - d) ** 2
    if topology == "buck_boost":
        return (1.0 - d) ** 2
    raise ValueError(topology)


def is_ccm(topology: str, d: float, l: float, r_load: float, fs: float) -> bool:
    return k_param(l, r_load, fs) > k_crit(topology, d)


def m_dcm(topology: str, d: float, l: float, r_load: float, fs: float) -> float:
    """Ideal (non-synchronous, diode) DCM conversion ratios."""
    k = k_param(l, r_load, fs)
    if topology == "buck":
        return 2.0 / (1.0 + math.sqrt(1.0 + 4.0 * k / d**2))
    if topology == "boost":
        return (1.0 + math.sqrt(1.0 + 4.0 * d**2 / k)) / 2.0
    if topology == "buck_boost":
        return -d / math.sqrt(k)
    raise ValueError(topology)


# ------------------------------------------------------------------- sizing

def inductor_for_ripple(topology: str, vin: float, vout: float, d: float,
                        delta_i: float, fs: float) -> float:
    """Inductance giving peak-to-peak current ripple delta_i (ideal CCM)."""
    vout = abs(vout)
    if topology in ("buck", "sync_buck"):
        return (vin - vout) * d / (delta_i * fs)
    if topology in ("boost", "sync_boost", "buck_boost", "sync_buck_boost", "sepic", "cuk", "four_switch"):
        return vin * d / (delta_i * fs)
    raise ValueError(topology)


def ripple_current(topology: str, vin: float, vout: float, d: float, l: float, fs: float) -> float:
    vout = abs(vout)
    if topology in ("buck", "sync_buck"):
        return (vin - vout) * d / (l * fs)
    return vin * d / (l * fs)


def output_cap_for_ripple(topology: str, i_out: float, d: float, delta_i: float,
                          delta_v: float, fs: float) -> float:
    """Output capacitance for peak-to-peak voltage ripple delta_v (capacitive part only).

    buck:          dV = dI / (8 C fs)       (triangular current into C)
    boost/others:  dV = Iout D / (C fs)     (C alone supplies the load while the switch is on)
    """
    if topology in ("buck", "sync_buck"):
        return delta_i / (8.0 * fs * delta_v)
    return i_out * d / (fs * delta_v)


def mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)
