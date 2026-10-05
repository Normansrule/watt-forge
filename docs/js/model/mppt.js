// mppt.js -- MPPT algorithm library, test profiles and closed-loop bench.
// Port of watt_forge/control/{rng,profiles,mppt,bench}.py, line for line and operation for
// operation, so tests/js/control.mjs can check it decision for decision against Python.
// REFERENCE ONLY: simulate and review before use.
import { panelVoltage, panelCurrent, globalMpp, defaultPanel } from './pv.js';

// ------------------------------------------------------------------ rng
const SQRT3 = 1.7320508075688772;
export class XorShift32 {
  constructor(seed = 2463534242) { this.x = (seed >>> 0) || 2463534242; }
  nextU32() { let x = this.x; x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; this.x = x; return x; }
  uniform() { return this.nextU32() / 4294967296; }
  normal() { const s = this.uniform() + this.uniform() + this.uniform() + this.uniform(); return (s - 2) * SQRT3; }
}

// ------------------------------------------------------------------ profiles
export const DT = 0.02;
export const HIGH_SLOPES = [10, 30, 50, 100];
export const LOW_SLOPES = [5, 10, 20, 50];
const DWELL = 10;
const n_ = (x) => Math.floor(x + 0.5);
function hold(g, seconds, t, out) { const n = n_(seconds / DT); for (let k = 0; k < n; k++) out.push({ g: [g, g, g], t }); }
function ramp(g0, g1, slope, t, out) {
  const n = n_(Math.abs(g1 - g0) / slope / DT);
  for (let k = 1; k <= n; k++) { const g = g0 + ((g1 - g0) * k) / n; out.push({ g: [g, g, g], t }); }
}
export function trapezoids(lo, hi, slopes, t = 25) {
  const out = [];
  hold(lo, DWELL, t, out);
  for (const s of slopes) { ramp(lo, hi, s, t, out); hold(hi, DWELL, t, out); ramp(hi, lo, s, t, out); hold(lo, DWELL, t, out); }
  return out;
}
export function clouds() {
  const seq = [[900, 0, 8], [250, 1, 6], [900, 2, 8], [400, 0.5, 5], [950, 0.8, 8], [150, 1.5, 6], [700, 3, 6], [300, 0.4, 4], [900, 1, 10]];
  const out = [];
  let g = seq[0][0];
  for (const [target, rampS, holdS] of seq) {
    if (rampS > 0) ramp(g, target, Math.abs(target - g) / rampS, 35, out);
    g = target;
    hold(g, holdS, 35, out);
  }
  return out;
}
export function shading() {
  const out = [];
  for (const [gs, seconds] of [[[900, 900, 900], 15], [[900, 900, 250], 25], [[900, 450, 200], 25], [[900, 900, 900], 15]]) {
    const n = n_(seconds / DT);
    for (let k = 0; k < n; k++) out.push({ g: [...gs], t: 45 });
  }
  return out;
}
export function steady() { const out = []; hold(800, 30, 45, out); return out; }
export function tuning() {
  const out = [];
  hold(200, 3, 30, out); ramp(200, 900, 25, 30, out); hold(900, 5, 30, out); ramp(900, 400, 500, 30, out);
  hold(400, 5, 30, out); ramp(400, 800, 40, 30, out); hold(800, 5, 30, out);
  for (let k = 0, n = n_(15 / DT); k < n; k++) out.push({ g: [800, 300, 800], t: 40 });
  for (let k = 0, n = n_(10 / DT); k < n; k++) out.push({ g: [800, 800, 800], t: 40 });
  return out;
}
export const PROFILES = {
  en50530_high: ['EN 50530-style ramps, 300-1000 W/m² (10, 30, 50, 100 W/m²/s)', () => trapezoids(300, 1000, HIGH_SLOPES)],
  en50530_low: ['EN 50530-style ramps, 100-500 W/m² (5, 10, 20, 50 W/m²/s)', () => trapezoids(100, 500, LOW_SLOPES)],
  clouds: ['Cloud edges: fast drops and recoveries', clouds],
  shading: ['Partial shading: one, then two substrings shaded', shading],
  steady: ['Steady 800 W/m²: start-up plus steady tracking', steady],
};
export const getProfile = (name) => (name === 'tuning' ? tuning() : PROFILES[name][1]());

// ------------------------------------------------------------------ trackers
export const V_MIN = 12, V_MAX = 60;
const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);

class Tracker {
  constructor(defaults, kw) {
    Object.assign(this, defaults);
    for (const [k, v] of Object.entries(kw || {})) {
      if (!(k in defaults)) throw new TypeError(`${this.constructor.name} has no parameter ${k}`);
      this[k] = v;
    }
    this.vref = 0; this.openRequest = false; this.voc = 0;
  }
  hi() { const h = 0.98 * this.voc; return h < V_MAX ? h : V_MAX; }
  reset(voc) { this.voc = voc; this.vref = clamp(0.8 * voc, V_MIN, this.hi()); }
}

export class PO extends Tracker {
  static key = 'po';
  static label = 'Perturb & observe (fixed step)';
  constructor(kw) { super({ step: 0.2, period: 1 }, kw); }
  reset(voc) { super.reset(voc); this.p_prev = -1; this.direction = -1; }
  update(v, i) {
    const p = v * i;
    if (this.p_prev >= 0 && p < this.p_prev) this.direction = -this.direction;
    this.p_prev = p;
    this.vref = clamp(this.vref + this.direction * this.step, V_MIN, this.hi());
  }
}

export class VSPO extends Tracker {
  static key = 'vspo';
  static label = 'Perturb & observe (variable step)';
  constructor(kw) { super({ gain: 0.04, step_min: 0.3, step_max: 2, period: 2 }, kw); }
  reset(voc) { super.reset(voc); this.p_prev = -1; this.v_prev = 0; this.direction = -1; this.step = 0.5; }
  update(v, i) {
    const p = v * i;
    if (this.p_prev >= 0) {
      const dv = v - this.v_prev, dp = p - this.p_prev;
      if (dp < 0) this.direction = -this.direction;
      if (dv > 0.05 || dv < -0.05) {
        let slope = dp / dv;
        if (slope < 0) slope = -slope;
        this.step = clamp(this.gain * slope, this.step_min, this.step_max);
      }
    }
    this.p_prev = p; this.v_prev = v;
    this.vref = clamp(this.vref + this.direction * this.step, V_MIN, this.hi());
  }
}

export class INC extends Tracker {
  static key = 'inc';
  static label = 'Incremental conductance (fixed step)';
  constructor(kw, defaults = { step: 0.3, tol: 0.001, period: 2 }) { super(defaults, kw); }
  reset(voc) { super.reset(voc); this.first = true; this.v_prev = 0; this.i_prev = 0; this.vref = this.vref - this.step; }
  direction(v, i) {
    const dv = v - this.v_prev, di = i - this.i_prev;
    const g = v > 1 ? i / v : 0;
    if (dv > -0.05 && dv < 0.05) {
      if (di > -0.02 && di < 0.02) return 0;
      return di > 0 ? 1 : -1;
    }
    const e = di / dv + g;
    if (e > -this.tol * g && e < this.tol * g) return 0;
    return e > 0 ? 1 : -1;
  }
  stepSize() { return this.step; }
  update(v, i) {
    if (!this.first) {
      const d = this.direction(v, i);
      this.vref = clamp(this.vref + d * this.stepSize(v, i), V_MIN, this.hi());
    }
    this.first = false;
    this.v_prev = v; this.i_prev = i;
  }
}

export class VSINC extends INC {
  static key = 'vsinc';
  static label = 'Incremental conductance (variable step)';
  constructor(kw) { super(kw, { gain: 0.08, step_min: 0.3, step_max: 2, tol: 0.03, period: 2, step: 0.5 }); }
  stepSize(v, i) {
    const dv = v - this.v_prev;
    if (dv > -0.05 && dv < 0.05) return this.step_min;
    let slope = (v * i - this.v_prev * this.i_prev) / dv;
    if (slope < 0) slope = -slope;
    return clamp(this.gain * slope, this.step_min, this.step_max);
  }
}

export class FOCV extends Tracker {
  static key = 'focv';
  static label = 'Fractional open-circuit voltage';
  constructor(kw) { super({ k: 0.84, every: 1000, period: 1 }, kw); }
  reset(voc) { super.reset(voc); this.count = 0; this.vref = clamp(this.k * voc, V_MIN, this.hi()); this.sampling = false; }
  update(v, i) {
    if (this.sampling) {
      this.sampling = false; this.openRequest = false; this.voc = v;
      this.vref = clamp(this.k * v, V_MIN, this.hi());
      return;
    }
    this.count += 1;
    if (this.count >= this.every) { this.count = 0; this.sampling = true; this.openRequest = true; }
  }
}

export const SIN10 = [0.0, 0.5877852522924731, 0.9510565162951535, 0.9510565162951536, 0.5877852522924732,
  1.2246467991473532e-16, -0.587785252292473, -0.9510565162951535, -0.9510565162951536, -0.5877852522924734];

export class ESC extends Tracker {
  static key = 'esc';
  static label = 'Extremum seeking (injected dither)';
  constructor(kw) { super({ amp: 0.8, gain: 0.016, hp: 0.8, period: 1 }, kw); }
  reset(voc) { super.reset(voc); this.vhat = this.vref; this.k = 0; this.p_prev = -1; this.hpf = 0; }
  update(v, i) {
    const p = v * i;
    if (this.p_prev >= 0) this.hpf = this.hp * (this.hpf + p - this.p_prev);
    this.p_prev = p;
    this.vhat = clamp(this.vhat + this.gain * this.hpf * SIN10[this.k], V_MIN, this.hi());
    this.k = (this.k + 1) % 10;
    this.vref = clamp(this.vhat + this.amp * SIN10[this.k], V_MIN, this.hi());
  }
}

export class PSO extends Tracker {
  static key = 'pso';
  static label = 'Particle swarm + variable-step P&O';
  constructor(kw = {}) {
    const { seed = 12345, ...rest } = kw;
    super({ n: 4, w: 0.4, c1: 1.0, c2: 1.6, restart: 0.25, period: 2 }, rest);
    this.rng = new XorShift32(seed);
    this.local = new VSPO();
  }
  spread() {
    const lo = V_MIN, hi = this.hi();
    this.x = []; for (let j = 0; j < this.n; j++) this.x.push(lo + ((hi - lo) * (j + 0.5)) / this.n);
    this.vel = new Array(this.n).fill(0); this.pbest = new Array(this.n).fill(-1); this.xbest = [...this.x];
    this.gbest_p = -1; this.gbest_x = this.x[0]; this.j = 0; this.iters = 0; this.searching = true; this.vref = this.x[0];
  }
  reset(voc) { super.reset(voc); this.spread(); this.p_track = 0; }
  update(v, i) {
    const p = v * i;
    if (this.searching) {
      if (p > this.pbest[this.j]) { this.pbest[this.j] = p; this.xbest[this.j] = this.x[this.j]; }
      if (p > this.gbest_p) { this.gbest_p = p; this.gbest_x = this.x[this.j]; }
      this.j += 1;
      if (this.j >= this.n) {
        this.j = 0; this.iters += 1;
        let spread = 0;
        const lo = V_MIN, hi = this.hi();
        for (let k = 0; k < this.n; k++) {
          const r1 = this.rng.uniform(), r2 = this.rng.uniform();
          this.vel[k] = this.w * this.vel[k] + this.c1 * r1 * (this.xbest[k] - this.x[k]) + this.c2 * r2 * (this.gbest_x - this.x[k]);
          this.x[k] = clamp(this.x[k] + this.vel[k], lo, hi);
          let d = this.x[k] - this.gbest_x;
          if (d < 0) d = -d;
          if (d > spread) spread = d;
        }
        if (spread < 0.5 || this.iters >= 15) {
          this.searching = false;
          this.local.reset(this.voc); this.local.vref = this.gbest_x;
          this.vref = this.gbest_x; this.p_track = this.gbest_p;
          return;
        }
      }
      this.vref = this.x[this.j];
      return;
    }
    if (this.p_track > 1) {
      const ratio = p / this.p_track;
      if (ratio < 1 - this.restart || ratio > 1 + this.restart) { this.spread(); return; }
    }
    this.p_track = 0.98 * this.p_track + 0.02 * p;
    this.local.update(v, i);
    this.vref = this.local.vref;
  }
}

export class SCAN extends Tracker {
  static key = 'scan';
  static label = 'Global scan + variable-step P&O';
  constructor(kw) { super({ points: 8, lo_frac: 0.25, rescan: 1500, drop: 0.45, period: 2 }, kw); this.local = new VSPO(); }
  start() {
    this.scanning = true; this.k = 0; this.best_p = -1; this.best_v = 0; this.top = this.hi();
    const lo = this.lo_frac * this.voc;
    this.bottom = lo > V_MIN ? lo : V_MIN;
    this.vref = this.top; this.since = 0;
  }
  reset(voc) { super.reset(voc); this.p_avg = 0; this.start(); }
  update(v, i) {
    const p = v * i;
    if (this.scanning) {
      if (p > this.best_p) { this.best_p = p; this.best_v = this.vref; }
      this.k += 1;
      if (this.k >= this.points) {
        this.scanning = false; this.local.reset(this.voc); this.local.vref = this.best_v;
        this.vref = this.best_v; this.p_avg = this.best_p;
        return;
      }
      this.vref = this.top - ((this.top - this.bottom) * this.k) / (this.points - 1);
      return;
    }
    this.since += 1;
    if (this.since >= this.rescan || (this.p_avg > 20 && p < this.drop * this.p_avg)) { this.start(); return; }
    this.p_avg = 0.97 * this.p_avg + 0.03 * p;
    this.local.update(v, i);
    this.vref = this.local.vref;
  }
}

export const ALGORITHMS = { po: PO, vspo: VSPO, inc: INC, vsinc: VSINC, focv: FOCV, esc: ESC, pso: PSO, scan: SCAN };
export const FAMILY = { po: 'Hill climbing', vspo: 'Hill climbing', inc: 'Hill climbing', vsinc: 'Hill climbing',
  focv: 'Model based', esc: 'Gradient (extremum seeking)', pso: 'Global search', scan: 'Global search' };
export const makeTracker = (key, kw = {}) => new ALGORITHMS[key](kw);

// ------------------------------------------------------------------ bench
export const ALPHA = 0.98;
export const SIGMA_V = 0.02, SIGMA_I = 0.01;
export const LSB_V = 72 / 4096, LSB_I = 20 / 4096;
export function quantize(x, lsb) { const q = Math.floor(x / lsb + 0.5) * lsb; return q > 0 ? q : 0; }

export class MppOracle {
  constructor(panel = defaultPanel()) { this.panel = panel; this.grids = new Map(); this.cache = new Map(); }
  grid(t) {
    if (!this.grids.has(t)) {
      const n = Math.floor(1200 / 2) + 1;
      const g = [0];
      for (let k = 1; k < n; k++) g.push(globalMpp([k * 2, k * 2, k * 2], t, this.panel).p);
      this.grids.set(t, g);
    }
    return this.grids.get(t);
  }
  pMpp(g, t) {
    if (g[0] === g[1] && g[1] === g[2]) {
      const grid = this.grid(t);
      const x = g[0] / 2;
      const k = Math.floor(x);
      if (k >= grid.length - 1) return grid[grid.length - 1];
      const f = x - k;
      return grid[k] + (grid[k + 1] - grid[k]) * f;
    }
    const key = `${g[0]},${g[1]},${g[2]},${t}`;
    if (!this.cache.has(key)) this.cache.set(key, globalMpp(g, t, this.panel));
    return this.cache.get(key).p;
  }
}

export class EtaTable {
  constructor(d) { this.vins = d.vin; this.pins = d.pin; this.eta = d.eta; }
  at(vin, pin) {
    if (pin <= 0) return 0;
    const vs = this.vins, ps = this.pins;
    vin = vin < vs[0] ? vs[0] : vin > vs[vs.length - 1] ? vs[vs.length - 1] : vin;
    if (pin < ps[0]) return (this.at(vin, ps[0]) * pin) / ps[0];
    pin = pin > ps[ps.length - 1] ? ps[ps.length - 1] : pin;
    let a = 0; while (a < vs.length - 2 && vin > vs[a + 1]) a++;
    let b = 0; while (b < ps.length - 2 && pin > ps[b + 1]) b++;
    const fa = (vin - vs[a]) / (vs[a + 1] - vs[a]);
    const fb = (pin - ps[b]) / (ps[b + 1] - ps[b]);
    const e = this.eta;
    const top = e[a][b] + (e[a][b + 1] - e[a][b]) * fb;
    const bot = e[a + 1][b] + (e[a + 1][b + 1] - e[a + 1][b]) * fb;
    return top + (bot - top) * fa;
  }
}

/** Closed-loop run. opts: { seed, noise, oracle, eta (EtaTable), panel, recordEvery, sigmaV, sigmaI, onTick } */
export function run(tracker, profile, opts = {}) {
  const panel = opts.panel || defaultPanel();
  const oracle = opts.oracle || new MppOracle(panel);
  const eta = opts.eta;
  const rng = new XorShift32(opts.seed ?? 7);
  const noise = opts.noise ?? true;
  const sigV = opts.sigmaV ?? SIGMA_V, sigI = opts.sigmaI ?? SIGMA_I;
  const rec = opts.recordEvery || 0;
  const dt = DT;
  const env0 = profile[0];
  const voc0 = panelVoltage(0, env0.g, env0.t, panel);
  let v = voc0;
  tracker.reset(quantize(voc0, LSB_V));
  const period = tracker.period, settle = Math.floor(period / 2);
  let sumV = 0, sumI = 0, nAvg = 0, tw = 0;
  let ePv = 0, eMpp = 0, eBatt = 0;
  const trace = rec ? { t: [], p: [], pmpp: [], v: [] } : null;
  for (let k = 0; k < profile.length; k++) {
    const { g, t: tc } = profile[k];
    const voc = panelVoltage(0, g, tc, panel);
    let vTrue, iTrue;
    if (tracker.openRequest) { vTrue = voc; iTrue = 0; }
    else {
      v = v + ALPHA * (tracker.vref - v);
      if (v > voc) v = voc;
      vTrue = v;
      iTrue = panelCurrent(vTrue, g, tc, panel, 32);
    }
    if (tracker.openRequest) v = voc;
    const pTrue = vTrue * iTrue;
    const pAvail = oracle.pMpp(g, tc);
    ePv += pTrue * dt;
    eMpp += pAvail * dt;
    if (eta) eBatt += pTrue * eta.at(vTrue, pTrue) * dt;
    let vm, im;
    if (noise) { vm = quantize(vTrue + sigV * rng.normal(), LSB_V); im = quantize(iTrue + sigI * rng.normal(), LSB_I); }
    else { vm = vTrue; im = iTrue; }
    if (trace && k % rec === 0) { trace.t.push(k * dt); trace.p.push(pTrue); trace.pmpp.push(pAvail); trace.v.push(vTrue); }
    if (tracker.openRequest) { tracker.update(vm, im); sumV = 0; sumI = 0; nAvg = 0; tw = 0; continue; }
    if (tw >= settle) { sumV += vm; sumI += im; nAvg += 1; }
    tw += 1;
    if (tw >= period) { tracker.update(sumV / nAvg, sumI / nAvg); sumV = 0; sumI = 0; nAvg = 0; tw = 0; }
  }
  const out = { eta_mppt: ePv / eMpp, eta_sys: eta ? eBatt / eMpp : null, e_mpp_J: eMpp, e_pv_J: ePv, e_batt_J: eBatt,
    e_lost_J: eMpp - ePv, seconds: profile.length * dt };
  if (trace) out.trace = trace;
  return out;
}
