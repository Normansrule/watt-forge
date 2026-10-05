// effctl.js -- converter-side efficiency controls on the flagship loss model.
// Port of watt_forge/control/efficiency.py (parity-tested by tests/js/control.mjs).
// REFERENCE ONLY: model predictions, simulate and review before use.
import * as F from './flagship.js';
import { panelCurrent, defaultPanel } from './pv.js';
import { XorShift32 } from './mppt.js';

export const FIXED_FS = 100e3;
export const TD_GRID = []; for (let k = 4; k < 51; k += 2) TD_GRID.push(k * 1e-9);
export const BURST_POWERS = [40, 60, 90, 120, 160];
export const BURST_FREQS = [250, 500, 1000, 2000, 5000, 10000];
export const BURST_MIN_CYCLES = 8;
export const E_WAKE = 4e-6;
export const C_IN_BULK = 66e-6, C_IN_MLCC_N = 6, C_IN_MLCC_EACH = 10e-6;
export const BURST_MAX_RIPPLE = 0.05;
export const SIGMA_V_SAMPLE = 0.02, SIGMA_I_SAMPLE = 0.01, AVG_SAMPLES = 250, MC_SEEDS = 20;
export const KAPPA_REF = 3.76, P_KAPPA_REF = 364.8, V_KAPPA_REF = 37.6;

function feasibleBest(rs) {
  let best = null;
  for (const r of rs) if (r.feasible && (best === null || r.loss_total < best.loss_total)) best = r;
  return best;
}
export function at(vin, vout, pout, fs, td = null, p = F.defaultParams()) {
  const q = td === null ? p : { ...p, t_dead: td };
  return feasibleBest(F.modesFor(vin, vout).map((m) => F.evaluate(vin, vout, pout, fs, m, q)));
}
export function fsCurve(vin, vout, pout, td = null, p = F.defaultParams()) {
  return p.f_candidates.map((fs) => { const r = at(vin, vout, pout, fs, td, p); return { fs, loss: r ? r.loss_total : null, mode: r ? r.mode : null }; });
}
export function fixedFs(vin, vout, pout, td = null, p = F.defaultParams()) {
  for (const fs of p.f_candidates.filter((f) => f >= FIXED_FS)) { const r = at(vin, vout, pout, fs, td, p); if (r) return r; }
  throw new Error('no feasible frequency');
}
export function tdCurve(vin, vout, pout, fs, p = F.defaultParams()) {
  return TD_GRID.map((td) => { const r = at(vin, vout, pout, fs, td, p); return { td, loss: r ? r.loss_total : null }; });
}

export class HillClimb {
  constructor(n, start, margin = 0.02, rest = 10) {
    Object.assign(this, { n, idx: start, margin, rest, base_cost: -1, probe: 0, direction: 1, fails: 0, resting: 0 });
  }
  update(cost) {
    if (this.resting > 0) { this.resting -= 1; if (this.resting === 0) this.base_cost = -1; return this.idx; }
    if (this.probe === 0) {
      this.base_cost = cost;
      let nxt = this.idx + this.direction;
      if (nxt < 0 || nxt >= this.n) { this.direction = -this.direction; nxt = this.idx + this.direction; }
      this.probe = this.direction; this.idx = nxt;
      return this.idx;
    }
    if (cost < this.base_cost - this.margin) { this.base_cost = cost; this.fails = 0; this.probe = 0; return this.idx; }
    this.idx -= this.probe; this.probe = 0; this.direction = -this.direction; this.fails += 1;
    if (this.fails >= 2) { this.fails = 0; this.resting = this.rest; }
    return this.idx;
  }
}

export function onlineSearch(costs, start, { updates = 60, sigma = 0.03, seed = 3, margin = 0.02 } = {}) {
  const rng = new XorShift32(seed);
  const hc = new HillClimb(costs.length, start, margin);
  let idx = start;
  const path = [idx];
  for (let u = 0; u < updates; u++) {
    let c = costs[idx];
    c = c === null ? 1e9 : c + sigma * rng.normal();
    idx = hc.update(c);
    path.push(idx);
  }
  const tail = path.slice(-20);
  let final = 0, bestCount = -1;
  for (let i = 0; i < costs.length; i++) {
    const n = tail.filter((x) => x === i).length;
    if (n > bestCount) { bestCount = n; final = i; }
  }
  return { path, final };
}

export function powerSigma(vin, pin) {
  const i = pin / vin;
  const perSample = Math.sqrt((i * SIGMA_V_SAMPLE) ** 2 + (vin * SIGMA_I_SAMPLE) ** 2);
  return perSample / Math.sqrt(AVG_SAMPLES);
}
export const kappaEstimate = (vin, pout) => KAPPA_REF * (pout / P_KAPPA_REF) * (V_KAPPA_REF / vin) ** 2;

export function monteCarlo(costs, start, sigma, seeds = MC_SEEDS, seed0 = 1) {
  const finals = [], paths = [];
  for (let k = 0; k < seeds; k++) {
    const r = onlineSearch(costs, start, { sigma, margin: 2 * sigma, seed: seed0 + k });
    finals.push(r.final); paths.push(r.path);
  }
  let opt = -1;
  costs.forEach((c, i) => { if (c !== null && (opt < 0 || c < costs[opt])) opt = i; });
  let mean = 0; for (const f of finals) mean += costs[f]; mean /= finals.length;
  let mode = 0, best = -1;
  for (let i = 0; i < costs.length; i++) { const n = finals.filter((x) => x === i).length; if (n > best) { best = n; mode = i; } }
  return { finals, mode, optimum: opt, hit_rate: finals.filter((x) => x === opt).length / finals.length, mean_cost: mean, path: paths[0] };
}

function bias(p, v) {
  const pts = p.cfly_bias_curve;
  if (v <= pts[0][0]) return pts[0][1];
  for (let k = 0; k < pts.length - 1; k++) {
    const [v0, k0] = pts[k], [v1, k1] = pts[k + 1];
    if (v0 <= v && v <= v1) return k0 + ((k1 - k0) * (v - v0)) / (v1 - v0);
  }
  return pts[pts.length - 1][1];
}
export const cIn = (vin, p = F.defaultParams()) => C_IN_BULK + C_IN_MLCC_N * C_IN_MLCC_EACH * bias(p, vin);

export function pvCurvature(vmp, g, tc, panel = defaultPanel(), h = 0.25) {
  const f = (v) => v * panelCurrent(v, [g, g, g], tc, panel);
  return Math.abs(f(vmp + h) - 2 * f(vmp) + f(vmp - h)) / (h * h);
}

export function burst(vin, vout, pout, kappa, p = F.defaultParams()) {
  const iPv = (pout + 1) / vin;
  const cin = cIn(vin, p);
  let best = null;
  for (const pb of BURST_POWERS) {
    if (pout >= 0.9 * pb) continue;
    const rb = F.best(vin, vout, pb, p);
    const delta = pout / pb;
    const stageB = rb.loss_stage;
    const aux = delta * p.p_aux_switching + (1 - delta) * p.p_aux_idle;
    for (const fb of BURST_FREQS) {
      if (delta / fb < BURST_MIN_CYCLES / rb.fs) continue;
      const dv = (iPv * (1 - delta)) / (fb * cin);
      if (dv > BURST_MAX_RIPPLE * vin) continue;
      const mismatch = (kappa * dv * dv) / 24;
      const wake = E_WAKE * fb;
      const loss = delta * stageB + aux + wake + mismatch;
      if (best === null || loss < best.loss_total) {
        best = { active: true, p_burst: pb, f_burst: fb, fs_burst: rb.fs, delta, dv_pp: dv, loss_total: loss,
          parts: { stage: delta * stageB, aux, wake, mismatch }, eta: pout / (pout + loss) };
      }
    }
  }
  return best || { active: false };
}

export function operatingPoint(vin, vout, pout, kappa = 0, p = F.defaultParams()) {
  const base = fixedFs(vin, vout, pout, null, p);
  const sigma = powerSigma(vin, pout + base.loss_total);
  const curve = fsCurve(vin, vout, pout, null, p);
  const costs = curve.map((c) => c.loss);
  const start = p.f_candidates.indexOf(FIXED_FS);
  const mf = monteCarlo(costs, start, sigma);
  const fsOn = p.f_candidates[mf.mode];
  const tdc = tdCurve(vin, vout, pout, fsOn, p);
  const tcosts = tdc.map((c) => c.loss);
  let tStart = 0;
  TD_GRID.forEach((td, i) => { if (Math.abs(td - p.t_dead) < Math.abs(TD_GRID[tStart] - p.t_dead)) tStart = i; });
  const mt = monteCarlo(tcosts, tStart, sigma, MC_SEEDS, 101);
  const lossFs = mf.mean_cost;
  const lossTd = lossFs + (mt.mean_cost - tcosts[tStart]);
  const b = kappa > 0 ? burst(vin, vout, pout, kappa, p) : { active: false };
  const lossBurst = b.active ? Math.min(lossTd, b.loss_total) : lossTd;
  let lossBypass = lossBurst, bypassMismatch = 0;
  if (Math.abs(vin - vout) <= 0.02 * vout) {
    bypassMismatch = 0.5 * kappa * (vin - vout) ** 2;
    lossBypass = Math.min(lossBurst, F.bypass(vin, pout, p).loss_total + bypassMismatch);
  }
  return {
    vin, vout, pout, sigma,
    loss: { base: base.loss_total, fs: lossFs, td: lossTd, burst: lossBurst, bypass: lossBypass },
    fs: { fixed: base.fs, online: fsOn, optimum: p.f_candidates[mf.optimum], hit_rate: mf.hit_rate, path: mf.path, finals: mf.finals, curve },
    td: { fixed: p.t_dead, online: TD_GRID[mt.mode], optimum: TD_GRID[mt.optimum], hit_rate: mt.hit_rate, path: mt.path, finals: mt.finals,
      loss_fixed: tcosts[tStart], curve: tdc },
    burst: b, bypass_mismatch: bypassMismatch,
  };
}
