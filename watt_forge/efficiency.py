"""Efficiency and solar weighted efficiency.

eta = Pout / (Pout + sum(P_loss))

Weighted efficiencies (weights verified 2026-09-30 via the PVsyst documentation,
see docs/REFERENCES.md):
  CEC  = 0.04 n10 + 0.05 n20 + 0.12 n30 + 0.21 n50 + 0.53 n75 + 0.05 n100
  Euro = 0.03 n5 + 0.06 n10 + 0.13 n20 + 0.10 n30 + 0.48 n50 + 0.20 n100
(nX = efficiency at X % of rated power). The CEC protocol also averages over
three DC input voltages; do that by calling cec() at each voltage and averaging.
"""
from __future__ import annotations

from typing import Callable, Dict, Mapping

CEC_WEIGHTS: Dict[float, float] = {0.10: 0.04, 0.20: 0.05, 0.30: 0.12, 0.50: 0.21, 0.75: 0.53, 1.00: 0.05}
EURO_WEIGHTS: Dict[float, float] = {0.05: 0.03, 0.10: 0.06, 0.20: 0.13, 0.30: 0.10, 0.50: 0.48, 1.00: 0.20}


def efficiency(p_out: float, losses: Mapping[str, float] | float) -> float:
    total = losses if isinstance(losses, (int, float)) else sum(losses.values())
    return p_out / (p_out + total)


def weighted(eta_at: Callable[[float], float], weights: Mapping[float, float]) -> float:
    """Weighted efficiency; eta_at(fraction_of_rated_power) -> efficiency."""
    return sum(w * eta_at(frac) for frac, w in weights.items())


def cec(eta_at: Callable[[float], float]) -> float:
    return weighted(eta_at, CEC_WEIGHTS)


def euro(eta_at: Callable[[float], float]) -> float:
    return weighted(eta_at, EURO_WEIGHTS)
