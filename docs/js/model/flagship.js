// flagship.js -- hybrid three-level GaN buck-boost: parameters, modulation, analytic loss model.
// Port of watt_forge/flagship/{params,pwm,model}.py (parity-tested against Python fixtures).
import * as C from './core.js';
import * as D from './devices.js';

export function defaultParams() {
  return {
    spec: { vin_min: 12, vin_max: 60, vout_min: 40, vout_nom: 48, vout_max: 58, p_max: 400, iin_max: 15 },
    switch: 'EPC2361', tj: 80, dyn_rds: 1.1, t_dead: 10e-9, t_min_pulse: 120e-9,
    coss_hyst_frac: 0.1, l_loop: 0.4e-9, bds: 'INV100FQ030C',
    l: 4.7e-6, dcr: 2.86e-3, dcr_tc: 0.0039, t_ind: 70, rac_factor: 2, i_sat: 59, k_b: 0.3 / 59, core_volume: 6e-6, core: 'ferrite_generic',
    cfly_n: 4, cfly_each: 10e-6, cfly_bias_curve: [[0, 1], [25, 0.65], [30, 0.6], [50, 0.45], [100, 0.2]], cfly_esr_each: 3e-3,
    esr_in: 1e-3, esr_out: 1e-3, r_shunt: 1e-3, r_pcb: 0.8e-3, p_aux_switching: 0.55, p_aux_idle: 0.3,
    f_candidates: [50e3, 75e3, 100e3, 125e3, 150e3, 200e3, 250e3, 300e3, 400e3],
    max_ripple_pp: 12, max_cfly_ripple: 0.1, bb_phase_steps: 8,
  };
}

export const pRated = (p, vin) => Math.min(p.spec.p_max, 0.97 * p.spec.iin_max * vin);

export function cflyEff(p, v) {
  const pts = p.cfly_bias_curve;
  let k;
  if (v <= pts[0][0]) k = pts[0][1];
  else if (v >= pts[pts.length - 1][0]) k = pts[pts.length - 1][1];
  else {
    k = pts[pts.length - 1][1];
    for (let i = 0; i < pts.length - 1; i++) {
      const [v0, k0] = pts[i], [v1, k1] = pts[i + 1];
      if (v0 <= v && v <= v1) { k = k0 + ((k1 - k0) * (v - v0)) / (v1 - v0); break; }
    }
  }
  return p.cfly_n * p.cfly_each * k;
}
const cflyEsr = (p) => p.cfly_esr_each / p.cfly_n;

// ------------------------------------------------------------------ modulation
function mod(x, T) {
  const y = ((x % T) + T) % T;
  return Math.abs(y - T) < 1e-15 * T ? 0 : y;
}
function onWin(t, start, dur, T) {
  if (dur <= 0) return false;
  if (dur >= T) return true;
  const rel = (((t - start) % T) + T) % T;
  return rel < dur;
}

export function build(d1, d2, phase, T, inActive, outActive) {
  const times = new Set([0, T]);
  const edges = [];
  if (inActive) {
    for (const [start, pair] of [[0, 'outer'], [T / 2, 'inner']]) {
      const ton = mod(start, T), toff = mod(start + d1 * T, T);
      times.add(ton); times.add(toff);
      edges.push({ t: ton, leg: 'in', pair, incoming: 'top' }, { t: toff, leg: 'in', pair, incoming: 'bottom' });
    }
  }
  if (outActive) {
    for (const [start, pair] of [[phase * T, 'outer'], [phase * T + T / 2, 'inner']]) {
      const ton = mod(start, T), toff = mod(start + d2 * T, T);
      times.add(ton); times.add(toff);
      edges.push({ t: ton, leg: 'out', pair, incoming: 'bottom' }, { t: toff, leg: 'out', pair, incoming: 'top' });
    }
  }
  const ts = [...times].sort((a, b) => a - b);
  const uniq = [ts[0]];
  for (const t of ts.slice(1)) if (t - uniq[uniq.length - 1] > 1e-12 * T) uniq.push(t);
  uniq[uniq.length - 1] = T;
  const segs = [];
  for (let i = 0; i < uniq.length - 1; i++) {
    const t0 = uniq[i], t1 = uniq[i + 1], tm = 0.5 * (t0 + t1);
    segs.push({
      t0, dur: t1 - t0,
      a: !inActive || onWin(tm, 0, d1 * T, T) ? 1 : 0,
      b: !inActive || onWin(tm, T / 2, d1 * T, T) ? 1 : 0,
      c: !outActive || !onWin(tm, phase * T, d2 * T, T) ? 1 : 0,
      d: !outActive || !onWin(tm, phase * T + T / 2, d2 * T, T) ? 1 : 0,
    });
  }
  edges.sort((x, y) => x.t - y.t);
  return { segs, edges };
}

export function idealRipple(vin, vout, l, segs, edges, T) {
  const dv = segs.map((s) => (vin * (s.a + s.b)) / 2 - (vout * (s.c + s.d)) / 2);
  let vbar = 0;
  segs.forEach((s, i) => { vbar += dv[i] * s.dur; });
  vbar /= T;
  const knots = [0];
  segs.forEach((s, i) => knots.push(knots[i] + ((dv[i] - vbar) / l) * s.dur));
  let area = 0;
  segs.forEach((s, k) => { area += (s.dur * (knots[k] + knots[k + 1])) / 2; });
  const mean = area / T;
  return { T, segs, edges, knots: knots.map((x) => x - mean), vbar };
}

export function rippleAt(w, t) {
  for (let k = 0; k < w.segs.length; k++) {
    const s = w.segs[k];
    if (t <= s.t0 + s.dur + 1e-18) {
      const f = s.dur <= 0 ? 0 : (t - s.t0) / s.dur;
      return w.knots[k] + (w.knots[k + 1] - w.knots[k]) * f;
    }
  }
  return w.knots[w.knots.length - 1];
}
const ripplePP = (w) => Math.max(...w.knots) - Math.min(...w.knots);

export function avgI(w, il, mask) {
  let acc = 0;
  w.segs.forEach((s, k) => {
    if (mask && !mask(s)) return;
    const p = il + w.knots[k], q = il + w.knots[k + 1];
    acc += (s.dur * (p + q)) / 2;
  });
  return acc / w.T;
}
export function avgI2(w, il, mask) {
  let acc = 0;
  w.segs.forEach((s, k) => {
    if (mask && !mask(s)) return;
    const p = il + w.knots[k], q = il + w.knots[k + 1];
    acc += (s.dur * (p * p + p * q + q * q)) / 3;
  });
  return acc / w.T;
}
const frac = (w, mask) => w.segs.reduce((a, s) => a + (mask(s) ? s.dur : 0), 0) / w.T;
export const cf1Mask = (s) => (s.a !== s.b ? 1 : 0);
export const cf2Mask = (s) => (s.c !== s.d ? 1 : 0);
export const inMask = (s) => s.a;
export const outMask = (s) => s.c;

function cfChargePP(w, il, which) {
  let q = 0, lo = 0, hi = 0;
  w.segs.forEach((s, k) => {
    let sign;
    if (which === 1) sign = s.a === 1 && s.b === 0 ? 1 : s.a === 0 && s.b === 1 ? -1 : 0;
    else sign = s.c === 1 && s.d === 0 ? -1 : s.c === 0 && s.d === 1 ? 1 : 0;
    const p = il + w.knots[k], r = il + w.knots[k + 1];
    q += (sign * s.dur * (p + r)) / 2;
    lo = Math.min(lo, q); hi = Math.max(hi, q);
  });
  return hi - lo;
}

// ------------------------------------------------------------------ model
export const rSw = (p) => D.rds(D.get(p.switch), p.tj) * p.dyn_rds;
export const dcrHot = (p) => p.dcr * (1 + p.dcr_tc * (p.t_ind - 25));
const rPath = (p) => 4 * rSw(p) + dcrHot(p) + p.r_pcb;
export function dutyLimits(p, fs) { const dmin = (p.t_min_pulse + p.t_dead) * fs; return [dmin, 1 - dmin]; }

function solveDuties(mode, vin, vout, iout, fs, p, phase) {
  const T = 1 / fs;
  const [dmin, dmax] = dutyLimits(p, fs);
  const rp = rPath(p);
  const inA = mode === 'buck' || mode === 'buckboost';
  const outA = mode === 'boost' || mode === 'buckboost';
  let il = iout * Math.max(vout / vin, 1);
  let d1 = 1, d2 = 0, w = null;
  for (let it = 0; it < 6; it++) {
    const drop = il * rp;
    if (mode === 'buck') { d1 = (vout + drop) / vin; d2 = 0; }
    else if (mode === 'boost') { d1 = 1; d2 = 1 - (vin - drop) / vout; }
    else {
      d1 = dmax; d2 = 1 - (d1 * vin - drop) / vout;
      if (d2 < dmin) { d2 = dmin; d1 = ((1 - d2) * vout + drop) / vin; }
    }
    const { segs, edges } = build(d1, d2, phase, T, inA, outA);
    w = idealRipple(vin, vout, p.l, segs, edges, T);
    const cFrac = frac(w, outMask);
    const corr = avgI(w, 0, outMask);
    il = (iout - corr) / cFrac;
  }
  let feasible = true, reason = '';
  if (inA && !(dmin - 1e-12 <= d1 && d1 <= dmax + 1e-12)) { feasible = false; reason = `buck duty ${d1.toFixed(3)} outside [${dmin.toFixed(3)},${dmax.toFixed(3)}]`; }
  if (outA && !(dmin - 1e-12 <= d2 && d2 <= dmax + 1e-12)) { feasible = false; reason = `boost duty ${d2.toFixed(3)} outside [${dmin.toFixed(3)},${dmax.toFixed(3)}]`; }
  if (mode === 'buck' && d1 > dmax) feasible = false;
  return { d1, d2, il, w, feasible, reason };
}

export function modeLabel(mode, d1, d2) {
  if (mode === 'boost' && Math.abs(d2 - 0.5) < 0.06) return 'boost (SC 1:2 region)';
  if (mode === 'buck' && Math.abs(d1 - 0.5) < 0.06) return 'buck (SC 2:1 region)';
  return mode;
}

export function evaluate(vin, vout, pout, fs, mode, p = defaultParams(), phase = null) {
  const dev = D.get(p.switch);
  const bds = D.get(p.bds);
  const iout = pout / vout;
  const inA = mode === 'buck' || mode === 'buckboost';
  const outA = mode === 'boost' || mode === 'buckboost';
  if (phase === null) {
    if (mode === 'buckboost') {
      let best = null;
      for (let k = 0; k < p.bb_phase_steps; k++) {
        const ph = k / p.bb_phase_steps;
        const r = solveDuties(mode, vin, vout, iout, fs, p, ph);
        const score = avgI2(r.w, r.il);
        if (best === null || score < best[0] - 1e-12) best = [score, ph];
      }
      phase = best[1];
    } else phase = 0;
  }
  const { d1, d2, il, w, feasible, reason } = solveDuties(mode, vin, vout, iout, fs, p, phase);
  const r = rSw(p), dcr = dcrHot(p);
  const i2 = avgI2(w, il), ac2 = i2 - il * il;
  const iinDc = avgI(w, il, inMask);
  const L = {};
  L.switch_conduction = 4 * r * i2;
  L.inductor_dcr = dcr * il * il + dcr * ac2;
  L.inductor_ac = dcr * (p.rac_factor - 1) * ac2;
  L.pcb_copper = p.r_pcb * i2;
  L.shunts = p.r_shunt * (iinDc * iinDc + iout * iout);
  L.bds_disconnect = D.rds(bds, p.tj) * iinDc * iinDc;
  let cf = 0;
  if (inA) cf += cflyEsr(p) * avgI2(w, il, cf1Mask);
  if (outA) cf += cflyEsr(p) * avgI2(w, il, cf2Mask);
  L.cfly_esr = cf;
  const iIn2 = avgI2(w, il, inMask), iOut2 = avgI2(w, il, outMask);
  L.cin_cout_esr = p.esr_in * Math.max(iIn2 - iinDc ** 2, 0) + p.esr_out * Math.max(iOut2 - iout ** 2, 0);
  let coss = 0, ov = 0, dead = 0, hyst = 0, ring = 0, nHard = 0;
  const tOn = D.tOverlap(dev, true), tOff = D.tOverlap(dev, false);
  for (const e of w.edges) {
    const ie = il + rippleAt(w, e.t);
    const v = (e.leg === 'in' ? vin : vout) / 2;
    const q = D.qoss(dev, v);
    const iNodeOut = e.leg === 'in' ? ie : -ie;
    const hard = e.incoming === 'top' ? iNodeOut > 0 : iNodeOut < 0;
    const ai = Math.abs(ie);
    hyst += p.coss_hyst_frac * D.eoss(dev, v);
    if (hard) {
      nHard++;
      ring += 0.5 * p.l_loop * ai * ai;
      coss += q * v;
      ov += 0.5 * v * ai * tOn;
      dead += (dev.vsd || 0) * ai * p.t_dead;
    } else {
      const rr = q > 0 ? Math.max(0, 1 - (ai * p.t_dead) / (2 * q)) : 0;
      coss += q * v * rr * rr;
      ov += 0.5 * v * ai * tOff;
      const trc = ai > 0 ? Math.max(0, p.t_dead - (2 * q) / ai) : 0;
      dead += (dev.vsd || 0) * ai * trc;
    }
  }
  L.coss = coss * fs; L.overlap = ov * fs; L.dead_time = dead * fs; L.coss_hysteresis = hyst * fs; L.loop_ringing = ring * fs;
  L.gate = 4 * ((inA ? 1 : 0) + (outA ? 1 : 0)) * D.qg(dev) * dev.vdrv * fs;
  const mat = C.MATERIALS[p.core];
  const k = C.steinmetzK(mat);
  const times = w.segs.map((s) => s.t0).concat([w.T]);
  const flux = w.knots.map((x) => p.k_b * (il + x));
  L.inductor_core = C.igsePiecewiseLinear(k, mat.alpha, mat.beta, times, flux) * p.core_volume;
  const stage = Object.values(L).reduce((a, b) => a + b, 0);
  L.aux = p.p_aux_switching;
  const total = stage + L.aux;
  const ripple = ripplePP(w);
  const ipk = Math.abs(il) + Math.max(Math.abs(Math.min(...w.knots)), Math.abs(Math.max(...w.knots)));
  let cfRip = 0;
  if (inA) cfRip = Math.max(cfRip, cfChargePP(w, il, 1) / cflyEff(p, vin / 2) / (vin / 2));
  if (outA) cfRip = Math.max(cfRip, cfChargePP(w, il, 2) / cflyEff(p, vout / 2) / (vout / 2));
  const violations = [];
  if (!feasible) violations.push(reason || 'duty infeasible');
  if (ripple > p.max_ripple_pp) violations.push(`ripple ${ripple.toFixed(1)} A > ${p.max_ripple_pp} A`);
  if (cfRip > p.max_cfly_ripple) violations.push(`flying-cap ripple ${(100 * cfRip).toFixed(1)}% > ${(100 * p.max_cfly_ripple).toFixed(0)}%`);
  if (ipk > 0.7 * p.i_sat) violations.push(`peak current ${ipk.toFixed(1)} A > 70% Isat`);
  return {
    vin, vout, pout, fs, mode, phase, d1, d2, il, iin: iinDc, iout, ripple_pp: ripple, i_peak: ipk, cfly_ripple: cfRip,
    n_hard: nHard, losses: L, loss_stage: stage, loss_total: total, eta_stage: pout / (pout + stage), eta: pout / (pout + total),
    feasible: violations.length === 0, violations, label: modeLabel(mode, d1, d2), waveform: w,
  };
}

export function modesFor(vin, vout) {
  if (vin > vout * 1.001) return ['buck', 'buckboost'];
  if (vin < vout * 0.999) return ['boost', 'buckboost'];
  return ['buckboost'];
}

export function best(vin, vout, pout, p = defaultParams()) {
  const cands = [];
  for (const mode of modesFor(vin, vout)) for (const fs of p.f_candidates) cands.push(evaluate(vin, vout, pout, fs, mode, p));
  const ok = cands.filter((r) => r.feasible);
  const pool = ok.length ? ok : cands;
  return pool.reduce((a, b) => (b.loss_total < a.loss_total ? b : a));
}

export function bypass(v, pout, p = defaultParams()) {
  const bds = D.get(p.bds);
  const i = pout / v;
  const L = { bds_path: 2 * D.rds(bds, p.tj) * i * i, shunts: 2 * p.r_shunt * i * i, pcb_copper: 0.5 * p.r_pcb * i * i };
  const stage = Object.values(L).reduce((a, b) => a + b, 0);
  L.aux = p.p_aux_idle;
  const total = stage + L.aux;
  return { vin: v, vout: v, pout, mode: 'bypass', label: 'bypass', fs: 0, losses: L, loss_stage: stage, loss_total: total,
    eta_stage: pout / (pout + stage), eta: pout / (pout + total), feasible: true, violations: [] };
}
