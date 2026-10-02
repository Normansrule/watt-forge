"""Inductor core loss: Steinmetz equation and the improved Generalized Steinmetz
Equation (iGSE) for non-sinusoidal flux.

Steinmetz (sinusoidal flux, peak Bpk):   Pv = k * f^alpha * Bpk^beta          [W/m^3]
iGSE (any waveform, peak-to-peak dB):    Pv = (1/T) * int k_i |dB/dt|^alpha (dB)^(beta-alpha) dt
  with k_i = k / ( (2*pi)^(alpha-1) * int_0^{2pi} |cos t|^alpha * 2^(beta-alpha) dt )
Reference: Venkatachalam, Sullivan, Abdallah, Tacca, COMPEL 2002, DOI 10.1109/CIPE.2002.1196712.
"""
from __future__ import annotations

import math
from typing import Sequence

# Generic material presets. These are ILLUSTRATIVE, not a specific vendor
# material: each is calibrated to a single anchor point that is typical for
# its class at ~100 C. Replace with the inductor maker's data (Coilcraft
# publishes a measured core-loss calculator, not Steinmetz coefficients).
MATERIALS = {
    "ferrite_generic": {"alpha": 1.46, "beta": 2.75, "anchor_f": 100e3, "anchor_b": 0.1, "anchor_pv": 300e3,
                        "label": "Generic MnZn power ferrite (illustrative)"},
    "powder_generic": {"alpha": 1.30, "beta": 2.20, "anchor_f": 100e3, "anchor_b": 0.1, "anchor_pv": 1.2e6,
                       "label": "Generic composite / powder core (illustrative)"},
}


def steinmetz_k(material: dict) -> float:
    """Solve k so that the material hits its anchor loss density."""
    return material["anchor_pv"] / (material["anchor_f"] ** material["alpha"] * material["anchor_b"] ** material["beta"])


def steinmetz(k: float, alpha: float, beta: float, f: float, b_pk: float) -> float:
    """Classic Steinmetz loss density [W/m^3] for sinusoidal flux of peak b_pk [T]."""
    return k * f**alpha * b_pk**beta


def _cos_integral(alpha: float) -> float:
    """int_0^{2pi} |cos t|^alpha dt = 2*sqrt(pi)*Gamma((alpha+1)/2)/Gamma(alpha/2+1)."""
    return 2.0 * math.sqrt(math.pi) * math.gamma((alpha + 1.0) / 2.0) / math.gamma(alpha / 2.0 + 1.0)


def igse_ki(k: float, alpha: float, beta: float) -> float:
    return k / ((2.0 * math.pi) ** (alpha - 1.0) * _cos_integral(alpha) * 2.0 ** (beta - alpha))


def igse_triangular(k: float, alpha: float, beta: float, f: float, delta_b: float, duty: float) -> float:
    """iGSE loss density for a triangular flux of peak-to-peak delta_b rising for duty*T."""
    ki = igse_ki(k, alpha, beta)
    d = min(max(duty, 1e-9), 1 - 1e-9)
    return ki * delta_b**beta * f**alpha * (d ** (1 - alpha) + (1 - d) ** (1 - alpha))


def igse_piecewise_linear(k: float, alpha: float, beta: float, times: Sequence[float], b: Sequence[float]) -> float:
    """iGSE loss density for a periodic piecewise-linear flux given at breakpoints.

    times: strictly increasing, times[0] = 0, times[-1] = T. b: flux at each time (b[-1] == b[0]).
    Uses the single major-loop peak-to-peak (max - min), which is exact for
    waveforms without minor loops (all waveforms in this repo).
    """
    period = times[-1] - times[0]
    dbpp = max(b) - min(b)
    if dbpp <= 0 or period <= 0:
        return 0.0
    ki = igse_ki(k, alpha, beta)
    acc = 0.0
    for i in range(len(times) - 1):
        tau = times[i + 1] - times[i]
        if tau <= 0:
            continue
        slope = abs(b[i + 1] - b[i]) / tau
        acc += slope**alpha * tau
    return ki * dbpp ** (beta - alpha) * acc / period


def igse_sampled(k: float, alpha: float, beta: float, b: Sequence[float], period: float) -> float:
    """iGSE for a uniformly sampled periodic flux (numerical check of the closed forms)."""
    n = len(b)
    dt = period / n
    times = [i * dt for i in range(n + 1)]
    return igse_piecewise_linear(k, alpha, beta, times, list(b) + [b[0]])
