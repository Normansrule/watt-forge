// control.js -- reference supervisory controller (MPPT + mode selection).
// Port of watt_forge/flagship/control.py, itself proven identical to the C reference
// (hardware/flagship/control/wf_ctrl.c). REFERENCE ONLY: simulate and review before use.
import { FS_LUT } from '../data/fs_lut.js';

export const S = { INIT: 0, PRECHARGE: 1, SWEEP: 2, TRACK: 3, BYPASS: 4, FAULT: 5 };
export const M = { OFF: 0, BUCK: 1, BUCKBOOST: 2, BOOST: 3, BYPASS: 4 };
export const STATE_NAMES = ['INIT', 'PRECHARGE', 'SWEEP', 'TRACK', 'BYPASS', 'FAULT'];
export const MODE_NAMES = ['OFF', 'BUCK', 'BUCK-BOOST', 'BOOST', 'BYPASS'];

const K = {
  VIN_START: 13, VIN_STOP: 11, VIN_OVP: 62, VIN_MIN_REF: 12, VIN_MAX_REF: 60, VOUT_MIN: 38, VOUT_MAX: 59.5, VOUT_CV: 57.6,
  IIN_OCP: 16, T_OTP: 100, T_OTP_CLR: 85, START_TICKS: 1000, PRECHARGE_TICKS: 50, FAULT_RETRY_TICKS: 5000, SWEEP_STEPS: 40,
  RESWEEP_TICKS: 300000, BYPASS_BAND: 0.02, BYPASS_ENTER_TICKS: 200, BYPASS_CHECK_TICKS: 2000, BYPASS_MIN_P: 20,
  M_BUCK_MAX: 0.97, M_BOOST_MIN: 1.03, M_HYST: 0.01, BB_D1: 0.95, STEP_INIT: 0.5, STEP_MIN: 0.1, STEP_MAX: 1.0,
  SMALL_DP: 0.002, BIG_DP: 0.02, SMALL_COUNT: 8,
};
export const CONST = K;

export class Ctrl {
  constructor(lut = FS_LUT, overrides = {}) {
    this.lut = lut;
    this.k = { ...K, ...overrides };
    Object.assign(this, { state: S.INIT, mode: M.OFF, ticks: 0, voc: 0, vin_ref: 0, p_prev: 0, direction: -1, step: this.k.STEP_INIT,
      small: 0, sweep_k: 0, sweep_best_p: 0, sweep_best_v: 0, sweep_hi: 0, sweep_lo: 0, since_sweep: 0, p_avg: 0, near: 0 });
  }
  fault(m) { const k = this.k; return m.vin > k.VIN_OVP || m.vout > k.VOUT_MAX || m.vout < k.VOUT_MIN || m.iin > k.IIN_OCP || m.temp > k.T_OTP; }
  clear(m) { const k = this.k; return m.vin <= k.VIN_OVP && k.VOUT_MIN + 0.5 <= m.vout && m.vout <= k.VOUT_MAX - 0.5 && m.iin <= k.IIN_OCP && m.temp <= k.T_OTP_CLR; }
  selectMode(m) {
    const k = this.k, ratio = m.vout / this.vin_ref, cur = this.mode;
    if (cur === M.BUCK) return ratio > k.M_BUCK_MAX + k.M_HYST ? M.BUCKBOOST : M.BUCK;
    if (cur === M.BOOST) return ratio < k.M_BOOST_MIN - k.M_HYST ? M.BUCKBOOST : M.BOOST;
    if (cur === M.BUCKBOOST) {
      if (ratio < k.M_BUCK_MAX - k.M_HYST) return M.BUCK;
      if (ratio > k.M_BOOST_MIN + k.M_HYST) return M.BOOST;
      return M.BUCKBOOST;
    }
    if (ratio < k.M_BUCK_MAX) return M.BUCK;
    if (ratio > k.M_BOOST_MIN) return M.BOOST;
    return M.BUCKBOOST;
  }
  fsFor(ratio, pFrac) {
    const me = this.lut.m_edges, pe = this.lut.p_edges, tab = this.lut.fs_hz;
    let i = 0, j = 0;
    while (i < me.length - 2 && ratio >= me[i + 1]) i++;
    while (j < pe.length - 2 && pFrac >= pe[j + 1]) j++;
    return tab[i][j];
  }
  clampRef() {
    let hi = this.k.VIN_MAX_REF;
    if (this.voc > 0 && this.voc < hi) hi = this.voc;
    if (this.vin_ref > hi) this.vin_ref = hi;
    if (this.vin_ref < this.k.VIN_MIN_REF) this.vin_ref = this.k.VIN_MIN_REF;
  }
  drive(m, out) {
    const mode = this.mode, ratio = m.vout / this.vin_ref, pFrac = (m.vin * m.iin) / this.lut.p_max;
    out.mode = mode; out.vin_ref = this.vin_ref;
    if (mode === M.BUCK) { out.d1 = ratio; out.d2 = 0; }
    else if (mode === M.BOOST) { out.d1 = 1; out.d2 = 1 - 1 / ratio; }
    else if (mode === M.BUCKBOOST) { let d2 = 1 - this.k.BB_D1 / ratio; if (d2 < 0.02) d2 = 0.02; out.d1 = this.k.BB_D1; out.d2 = d2; }
    if (mode === M.BUCK || mode === M.BOOST || mode === M.BUCKBOOST) out.fs = this.fsFor(ratio, pFrac);
  }
  startSweep() {
    const k = this.k;
    this.state = S.SWEEP; this.ticks = 0; this.sweep_k = 0; this.sweep_best_p = 0; this.sweep_best_v = 0;
    let hi = 0.95 * this.voc; if (hi > k.VIN_MAX_REF) hi = k.VIN_MAX_REF;
    let lo = 0.45 * this.voc; if (lo < k.VIN_MIN_REF) lo = k.VIN_MIN_REF;
    this.sweep_hi = hi; this.sweep_lo = lo; this.vin_ref = hi; this.mode = M.OFF;
  }
  track(m) {
    const k = this.k, p = m.vin * m.iin;
    this.since_sweep++;
    if (m.vout > k.VOUT_CV) {
      this.vin_ref += 0.2; this.clampRef(); this.mode = this.selectMode(m); this.p_prev = p; this.p_avg = p; return;
    }
    this.p_avg = 0.99 * this.p_avg + 0.01 * p;
    if (this.since_sweep >= k.RESWEEP_TICKS || (this.p_avg > 50 && p < 0.7 * this.p_avg)) {
      this.voc = this.voc > 0 ? this.voc : m.vin; this.startSweep(); return;
    }
    const dp = p - this.p_prev;
    if (dp < 0) this.direction = -this.direction;
    const mag = dp >= 0 ? dp : -dp, scale = p > 1 ? p : 1;
    if (mag < k.SMALL_DP * scale) {
      this.small++;
      if (this.small >= k.SMALL_COUNT) { this.step *= 0.5; if (this.step < k.STEP_MIN) this.step = k.STEP_MIN; this.small = 0; }
    } else {
      this.small = 0;
      if (mag > k.BIG_DP * scale) { this.step *= 2; if (this.step > k.STEP_MAX) this.step = k.STEP_MAX; }
    }
    this.vin_ref += this.direction * this.step;
    this.clampRef();
    this.p_prev = p;
    this.mode = this.selectMode(m);
    let dv = this.vin_ref - m.vout; if (dv < 0) dv = -dv;
    if (dv < k.BYPASS_BAND * m.vout && p > k.BYPASS_MIN_P) this.near++; else this.near = 0;
    if (this.near >= k.BYPASS_ENTER_TICKS) { this.state = S.BYPASS; this.ticks = 0; this.near = 0; this.mode = M.BYPASS; this.vin_ref = m.vout; }
  }
  tick(m) {
    const k = this.k;
    const out = { state: S.INIT, mode: M.OFF, vin_ref: 0, fs: 0, d1: 0, d2: 0 };
    this.ticks++;
    if (this.state !== S.FAULT && this.fault(m)) { this.state = S.FAULT; this.mode = M.OFF; this.ticks = 0; }
    if (this.state !== S.INIT && this.state !== S.FAULT && m.vin < k.VIN_STOP) { this.state = S.INIT; this.mode = M.OFF; this.ticks = 0; }
    if (this.state === S.FAULT) {
      if (!this.clear(m)) this.ticks = 0; else if (this.ticks >= k.FAULT_RETRY_TICKS) { this.state = S.INIT; this.ticks = 0; }
    } else if (this.state === S.INIT) {
      this.mode = M.OFF;
      if (m.vin < k.VIN_START) this.ticks = 0;
      else if (this.ticks >= k.START_TICKS) { this.voc = m.vin; this.state = S.PRECHARGE; this.ticks = 0; }
    } else if (this.state === S.PRECHARGE) {
      if (this.ticks >= k.PRECHARGE_TICKS) this.startSweep();
    } else if (this.state === S.SWEEP) {
      if (this.sweep_k > 0) { const p = m.vin * m.iin; if (p > this.sweep_best_p) { this.sweep_best_p = p; this.sweep_best_v = this.vin_ref; } }
      if (this.sweep_k >= k.SWEEP_STEPS) {
        this.vin_ref = this.sweep_best_p > 0 ? this.sweep_best_v : this.sweep_hi;
        this.state = S.TRACK; this.ticks = 0; this.p_prev = this.sweep_best_p; this.step = k.STEP_INIT; this.small = 0; this.near = 0;
        this.p_avg = this.sweep_best_p; this.since_sweep = 0; this.direction = -1;
      } else {
        this.vin_ref = this.sweep_hi - ((this.sweep_hi - this.sweep_lo) * this.sweep_k) / (k.SWEEP_STEPS - 1);
        this.sweep_k++; this.mode = this.selectMode(m); this.drive(m, out);
      }
    } else if (this.state === S.TRACK) {
      this.track(m);
    } else if (this.state === S.BYPASS) {
      this.mode = M.BYPASS; this.vin_ref = m.vout;
      if (this.ticks >= k.BYPASS_CHECK_TICKS) {
        this.state = S.TRACK; this.ticks = 0; this.mode = this.selectMode(m);
        this.p_prev = m.vin * m.iin; this.step = k.STEP_INIT; this.small = 0; this.near = 0; this.direction = -1;
      }
    }
    out.state = this.state;
    if (this.state === S.INIT || this.state === S.PRECHARGE || this.state === S.FAULT) Object.assign(out, { mode: M.OFF, vin_ref: 0, fs: 0, d1: 0, d2: 0 });
    else if (this.state === S.BYPASS) Object.assign(out, { mode: M.BYPASS, vin_ref: this.vin_ref, fs: 0, d1: 1, d2: 0 });
    else if (this.state === S.TRACK) this.drive(m, out);
    return out;
  }
}

export const line = (o) => `${o.state} ${o.mode} ${o.vin_ref.toFixed(6)} ${o.fs.toFixed(1)} ${o.d1.toFixed(6)} ${o.d2.toFixed(6)}`;
