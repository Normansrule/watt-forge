"""Flagship design parameters: hybrid three-level (flying-capacitor) four-switch GaN buck-boost.

Every value is either (a) taken from a verified datasheet (see data/devices.json
and hardware/flagship/BOM.csv) or (b) an ESTIMATE, labelled as such. Estimates are
what a careful designer would assume before measuring; they are the first
thing to replace with lab data.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Tuple


@dataclass
class Spec:
    vin_min: float = 12.0      # V, panel operating range (Voc max 60 V)
    vin_max: float = 60.0
    vout_min: float = 40.0     # V, 48 V-nominal battery bus
    vout_nom: float = 48.0
    vout_max: float = 58.0
    p_max: float = 400.0       # W output
    iin_max: float = 15.0      # A input-current limit (sets derating below ~27 V)

    def p_rated(self, vin: float) -> float:
        """Rated output power at a given input voltage (input-current limited at low Vin)."""
        return min(self.p_max, 0.97 * self.iin_max * vin)


@dataclass
class Params:
    spec: Spec = field(default_factory=Spec)
    # --- power switches (8x, two 3-level legs)
    switch: str = "EPC2361"
    tj: float = 80.0                     # C, ESTIMATE of junction temperature at rated load
    dyn_rds: float = 1.10                # ESTIMATE: dynamic Rds(on) allowance for GaN (x on hot Rds)
    t_dead: float = 10e-9                # s, dead time per transition
    t_min_pulse: float = 120e-9          # s, shortest pulse the modulator/driver chain allows
    coss_hyst_frac: float = 0.10         # ESTIMATE: GaN Coss hysteresis loss per charge/discharge cycle, fraction of Eoss
    l_loop: float = 0.4e-9               # H ESTIMATE: commutation-loop inductance (energy rings out on hard edges)
    # --- bidirectional GaN input disconnect / bypass
    bds: str = "INV100FQ030C"
    # --- inductor: Coilcraft SER2918H-472 (4.7 uH, DCR 2.60/2.86 mOhm, Isat 59 A @10 %)
    l: float = 4.7e-6
    dcr: float = 2.86e-3                 # max, 25 C
    dcr_tc: float = 0.0039               # copper tempco
    t_ind: float = 70.0                  # C ESTIMATE
    rac_factor: float = 2.0              # ESTIMATE: winding R at ripple frequency / DCR
    i_sat: float = 59.0
    k_b: float = 0.30 / 59.0             # T per A: ASSUMES ~0.30 T at Isat (gapped ferrite)
    core_volume: float = 6.0e-6          # m^3 ESTIMATE for a 29x29x18 mm ferrite inductor
    core: str = "ferrite_generic"
    # --- flying capacitors: 4x TDK C5750X7S2A106K230KB (10 uF, 100 V, X7S, 2220) per leg
    cfly_n: int = 4
    cfly_each: float = 10e-6
    cfly_bias_curve: Tuple[Tuple[float, float], ...] = ((0, 1.0), (25, 0.65), (30, 0.60), (50, 0.45), (100, 0.20))
    cfly_esr_each: float = 3e-3          # ohm ESTIMATE at the switching frequency
    # --- input / output capacitor banks (AC ESR seen by ripple currents)
    esr_in: float = 1.0e-3               # ESTIMATE
    esr_out: float = 1.0e-3              # ESTIMATE
    # --- sense & copper
    r_shunt: float = 1.0e-3              # Bourns CSS2H-3920R-1L00F in the inductor path
    r_pcb: float = 0.8e-3                # ESTIMATE total loop copper (2 oz, short loops)
    # --- housekeeping
    p_aux_switching: float = 0.55        # W ESTIMATE: MCU, drivers, isolated gate supplies, sensing
    p_aux_idle: float = 0.30             # W ESTIMATE in bypass (legs idle)
    # --- frequency schedule and constraints
    f_candidates: Tuple[float, ...] = (50e3, 75e3, 100e3, 125e3, 150e3, 200e3, 250e3, 300e3, 400e3)
    max_ripple_pp: float = 12.0          # A peak-to-peak inductor ripple limit (EMI / cap ripple)
    max_cfly_ripple: float = 0.10        # fraction of the flying-cap DC voltage
    bb_phase_steps: int = 8              # phase-shift candidates between legs in buck-boost mode

    def cfly_eff(self, v_dc: float) -> float:
        """Effective flying capacitance at DC bias v_dc (X7S derating, TDK chart, approximate)."""
        pts = self.cfly_bias_curve
        if v_dc <= pts[0][0]:
            k = pts[0][1]
        elif v_dc >= pts[-1][0]:
            k = pts[-1][1]
        else:
            k = pts[-1][1]
            for (v0, k0), (v1, k1) in zip(pts, pts[1:]):
                if v0 <= v_dc <= v1:
                    k = k0 + (k1 - k0) * (v_dc - v0) / (v1 - v0)
                    break
        return self.cfly_n * self.cfly_each * k

    def cfly_esr(self) -> float:
        return self.cfly_esr_each / self.cfly_n

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cfly_bias_curve"] = [list(p) for p in self.cfly_bias_curve]
        d["f_candidates"] = list(self.f_candidates)
        return d
