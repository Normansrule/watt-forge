"""Reference controller (Python) for the flagship converter.

REFERENCE ONLY. The C file hardware/flagship/control/wf_ctrl.c implements the same
state machine line for line and tests/test_control.py proves the two produce identical
outputs, in closed loop with the PV panel model. Simulate and review before use; this
is not production firmware.

State machine (1 kHz tick):
    INIT -> PRECHARGE -> SWEEP -> TRACK <-> BYPASS
                 any -> FAULT (latched, auto-retry after the fault clears for 5 s)
    TRACK: perturb & observe (P&O) maximum power point tracking with an adaptive step,
           plus mode selection (BUCK / BUCKBOOST / BOOST) with hysteresis on M = Vout/Vin_ref,
           plus a constant-voltage battery limit.
    BYPASS: when the maximum power point sits within 2% of the battery voltage, the panel is
           tied straight to the battery through the bidirectional GaN switch and switching stops.
           It re-checks every 2 s.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# ---- states and modes (must match wf_ctrl.h)
S_INIT, S_PRECHARGE, S_SWEEP, S_TRACK, S_BYPASS, S_FAULT = range(6)
M_OFF, M_BUCK, M_BUCKBOOST, M_BOOST, M_BYPASS = range(5)
STATE_NAMES = ["INIT", "PRECHARGE", "SWEEP", "TRACK", "BYPASS", "FAULT"]
MODE_NAMES = ["OFF", "BUCK", "BUCKBOOST", "BOOST", "BYPASS"]

VIN_START, VIN_STOP, VIN_OVP = 13.0, 11.0, 62.0
VIN_MIN_REF, VIN_MAX_REF = 12.0, 60.0
VOUT_MIN, VOUT_MAX, VOUT_CV = 38.0, 59.5, 57.6
IIN_OCP, T_OTP, T_OTP_CLR = 16.0, 100.0, 85.0
START_TICKS, PRECHARGE_TICKS, FAULT_RETRY_TICKS = 1000, 50, 5000
SWEEP_STEPS = 40
RESWEEP_TICKS = 300000
BYPASS_BAND, BYPASS_ENTER_TICKS, BYPASS_CHECK_TICKS, BYPASS_MIN_P = 0.02, 200, 2000, 20.0
M_BUCK_MAX, M_BOOST_MIN, M_HYST = 0.97, 1.03, 0.01
BB_D1 = 0.95
STEP_INIT, STEP_MIN, STEP_MAX = 0.5, 0.1, 1.0
SMALL_DP, BIG_DP, SMALL_COUNT = 0.002, 0.02, 8

LUT_PATH = Path(__file__).resolve().parents[2] / "data" / "fs_lut.json"


def load_lut(path: Path = LUT_PATH) -> dict:
    return json.loads(Path(path).read_text())


@dataclass
class Meas:
    vin: float
    iin: float
    vout: float
    iout: float = 0.0
    temp: float = 40.0


@dataclass
class Out:
    state: int = S_INIT
    mode: int = M_OFF
    vin_ref: float = 0.0
    fs: float = 0.0
    d1: float = 0.0
    d2: float = 0.0

    def line(self) -> str:
        return f"{self.state} {self.mode} {self.vin_ref:.6f} {self.fs:.1f} {self.d1:.6f} {self.d2:.6f}"


@dataclass
class Ctrl:
    lut: dict = field(default_factory=load_lut)
    state: int = S_INIT
    mode: int = M_OFF
    ticks: int = 0
    voc: float = 0.0
    vin_ref: float = 0.0
    p_prev: float = 0.0
    direction: float = -1.0
    step: float = STEP_INIT
    small: int = 0
    sweep_k: int = 0
    sweep_best_p: float = 0.0
    sweep_best_v: float = 0.0
    sweep_hi: float = 0.0
    sweep_lo: float = 0.0
    since_sweep: int = 0
    p_avg: float = 0.0
    near: int = 0

    # ------------------------------------------------------------------
    def _fault(self, m: Meas) -> bool:
        return (m.vin > VIN_OVP or m.vout > VOUT_MAX or m.vout < VOUT_MIN or m.iin > IIN_OCP or m.temp > T_OTP)

    def _clear(self, m: Meas) -> bool:
        return (m.vin <= VIN_OVP and VOUT_MIN + 0.5 <= m.vout <= VOUT_MAX - 0.5 and m.iin <= IIN_OCP and m.temp <= T_OTP_CLR)

    def _select_mode(self, m: Meas) -> int:
        ratio = m.vout / self.vin_ref
        cur = self.mode
        if cur == M_BUCK:
            return M_BUCKBOOST if ratio > M_BUCK_MAX + M_HYST else M_BUCK
        if cur == M_BOOST:
            return M_BUCKBOOST if ratio < M_BOOST_MIN - M_HYST else M_BOOST
        if cur == M_BUCKBOOST:
            if ratio < M_BUCK_MAX - M_HYST:
                return M_BUCK
            if ratio > M_BOOST_MIN + M_HYST:
                return M_BOOST
            return M_BUCKBOOST
        if ratio < M_BUCK_MAX:
            return M_BUCK
        if ratio > M_BOOST_MIN:
            return M_BOOST
        return M_BUCKBOOST

    def _fs(self, ratio: float, p_frac: float) -> float:
        me, pe, tab = self.lut["m_edges"], self.lut["p_edges"], self.lut["fs_hz"]
        i = 0
        while i < len(me) - 2 and ratio >= me[i + 1]:
            i += 1
        j = 0
        while j < len(pe) - 2 and p_frac >= pe[j + 1]:
            j += 1
        return float(tab[i][j])

    def _clamp_ref(self):
        hi = VIN_MAX_REF
        if self.voc > 0.0 and self.voc < hi:
            hi = self.voc
        if self.vin_ref > hi:
            self.vin_ref = hi
        if self.vin_ref < VIN_MIN_REF:
            self.vin_ref = VIN_MIN_REF

    def _drive(self, m: Meas, out: Out):
        """Duty feed-forward and frequency from the lookup table (the inner loop trims)."""
        mode = self.mode
        ratio = m.vout / self.vin_ref
        p_frac = m.vin * m.iin / self.lut["p_max"]
        out.mode = mode
        out.vin_ref = self.vin_ref
        if mode == M_BUCK:
            out.d1, out.d2 = ratio, 0.0
        elif mode == M_BOOST:
            out.d1, out.d2 = 1.0, 1.0 - 1.0 / ratio
        elif mode == M_BUCKBOOST:
            d2 = 1.0 - BB_D1 / ratio
            if d2 < 0.02:
                d2 = 0.02
            out.d1, out.d2 = BB_D1, d2
        if mode in (M_BUCK, M_BOOST, M_BUCKBOOST):
            out.fs = self._fs(ratio, p_frac)

    # ------------------------------------------------------------------
    def step_once(self, m: Meas) -> Out:
        out = Out()
        self.ticks += 1
        if self.state != S_FAULT and self._fault(m):
            self.state, self.mode, self.ticks = S_FAULT, M_OFF, 0
        if self.state not in (S_INIT, S_FAULT) and m.vin < VIN_STOP:
            self.state, self.mode, self.ticks = S_INIT, M_OFF, 0

        if self.state == S_FAULT:
            if not self._clear(m):
                self.ticks = 0
            elif self.ticks >= FAULT_RETRY_TICKS:
                self.state, self.ticks = S_INIT, 0
        elif self.state == S_INIT:
            self.mode = M_OFF
            if m.vin < VIN_START:
                self.ticks = 0
            elif self.ticks >= START_TICKS:
                self.voc = m.vin
                self.state, self.ticks = S_PRECHARGE, 0
        elif self.state == S_PRECHARGE:
            if self.ticks >= PRECHARGE_TICKS:
                self._start_sweep()
        elif self.state == S_SWEEP:
            if self.sweep_k > 0:
                p = m.vin * m.iin
                if p > self.sweep_best_p:
                    self.sweep_best_p, self.sweep_best_v = p, self.vin_ref
            if self.sweep_k >= SWEEP_STEPS:
                self.vin_ref = self.sweep_best_v if self.sweep_best_p > 0.0 else self.sweep_hi
                self.state, self.ticks = S_TRACK, 0
                self.p_prev, self.step, self.small, self.near = self.sweep_best_p, STEP_INIT, 0, 0
                self.p_avg = self.sweep_best_p
                self.since_sweep = 0
                self.direction = -1.0
            else:
                self.vin_ref = self.sweep_hi - (self.sweep_hi - self.sweep_lo) * self.sweep_k / (SWEEP_STEPS - 1)
                self.sweep_k += 1
                self.mode = self._select_mode(m)
                self._drive(m, out)
        elif self.state == S_TRACK:
            self._track(m, out)
        elif self.state == S_BYPASS:
            self.mode = M_BYPASS
            self.vin_ref = m.vout
            if self.ticks >= BYPASS_CHECK_TICKS:
                self.state, self.ticks = S_TRACK, 0
                self.mode = self._select_mode(m)
                self.p_prev, self.step, self.small, self.near = m.vin * m.iin, STEP_INIT, 0, 0
                self.direction = -1.0

        out.state = self.state
        if self.state in (S_INIT, S_PRECHARGE, S_FAULT):
            out.mode, out.vin_ref, out.fs, out.d1, out.d2 = M_OFF, 0.0, 0.0, 0.0, 0.0
        elif self.state == S_BYPASS:
            out.mode, out.vin_ref, out.fs, out.d1, out.d2 = M_BYPASS, self.vin_ref, 0.0, 1.0, 0.0
        elif self.state in (S_TRACK,):
            self._drive(m, out)
        return out

    def _start_sweep(self):
        self.state, self.ticks = S_SWEEP, 0
        self.sweep_k, self.sweep_best_p, self.sweep_best_v = 0, 0.0, 0.0
        hi = 0.95 * self.voc
        if hi > VIN_MAX_REF:
            hi = VIN_MAX_REF
        lo = 0.45 * self.voc
        if lo < VIN_MIN_REF:
            lo = VIN_MIN_REF
        self.sweep_hi, self.sweep_lo = hi, lo
        self.vin_ref = hi
        self.mode = M_OFF

    def _track(self, m: Meas, out: Out):
        p = m.vin * m.iin
        self.since_sweep += 1
        if m.vout > VOUT_CV:
            # constant-voltage limit: back off toward Voc (less power into a full battery).
            # Power is falling on purpose here, so the sudden-drop detector is re-armed.
            self.vin_ref += 0.2
            self._clamp_ref()
            self.mode = self._select_mode(m)
            self.p_prev = p
            self.p_avg = p
            return
        self.p_avg = 0.99 * self.p_avg + 0.01 * p
        if self.since_sweep >= RESWEEP_TICKS or (self.p_avg > 50.0 and p < 0.7 * self.p_avg):
            self.voc = self.voc if self.voc > 0.0 else m.vin
            self._start_sweep()
            return
        dp = p - self.p_prev
        if dp < 0.0:
            self.direction = -self.direction
        mag = dp if dp >= 0.0 else -dp
        scale = p if p > 1.0 else 1.0
        if mag < SMALL_DP * scale:
            self.small += 1
            if self.small >= SMALL_COUNT:
                self.step = self.step * 0.5
                if self.step < STEP_MIN:
                    self.step = STEP_MIN
                self.small = 0
        else:
            self.small = 0
            if mag > BIG_DP * scale:
                self.step = self.step * 2.0
                if self.step > STEP_MAX:
                    self.step = STEP_MAX
        self.vin_ref += self.direction * self.step
        self._clamp_ref()
        self.p_prev = p
        self.mode = self._select_mode(m)
        # bypass decision
        dv = self.vin_ref - m.vout
        if dv < 0.0:
            dv = -dv
        if dv < BYPASS_BAND * m.vout and p > BYPASS_MIN_P:
            self.near += 1
        else:
            self.near = 0
        if self.near >= BYPASS_ENTER_TICKS:
            self.state, self.ticks, self.near = S_BYPASS, 0, 0
            self.mode = M_BYPASS
            self.vin_ref = m.vout


def run_closed_loop(profile: List[dict], panel=None, vout0: float = 48.0, ctrl: Ctrl | None = None):
    """Drive the controller with the PV panel model. profile: list of per-tick dicts
    with 'g' (list of substring irradiances) and 't' (cell temperature)."""
    from .. import pv
    panel = panel or pv.Panel()
    ctrl = ctrl or Ctrl()
    vout = vout0
    out = Out()
    trace = []
    for k, env in enumerate(profile):
        g, tc = env["g"], env["t"]
        if out.state in (S_TRACK, S_SWEEP, S_BYPASS) and out.mode != M_OFF:
            vin = out.vin_ref
            iin = pv.panel_current(vin, g, tc, panel)
        else:
            vin = pv.panel_voltage(0.0, g, tc, panel)
            iin = 0.0
        meas = Meas(vin=vin, iin=iin, vout=env.get("vout", vout), temp=env.get("temp", 40.0))
        out = ctrl.step_once(meas)
        trace.append((meas, out))
    return trace
