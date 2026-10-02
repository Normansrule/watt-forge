// core.js -- conversion ratios, loss primitives, magnetics (Steinmetz / iGSE),
// switched-capacitor limits and weighted efficiency.
// Line-for-line port of watt_forge/{ratios,losses,magnetics,switched_cap,efficiency}.py;
// tests/js/parity.mjs checks every function against Python fixtures.

// ------------------------------------------------------------------ ratios
export const mBuck = (d) => d;
export const mBoost = (d) => 1 / (1 - d);
export const mBuckBoost = (d) => -d / (1 - d);
export const mSepic = (d) => d / (1 - d);
export const mCuk = (d) => -d / (1 - d);
export const mFlyback = (d, n) => (n * d) / (1 - d);
export const mFourSwitch = (d1, d2) => d1 / (1 - d2);

export function dutyForRatio(top, m, n = 1) {
  const a = Math.abs(m);
  if (top === 'buck' || top === 'sync_buck') return a;
  if (top === 'boost' || top === 'sync_boost') return 1 - 1 / a;
  if (['buck_boost', 'sync_buck_boost', 'sepic', 'cuk'].includes(top)) return a / (1 + a);
  if (top === 'flyback') return a / (n + a);
  throw new Error('unknown topology ' + top);
}

export const mBuckLossy = (d, r, ron, rl) => d / (1 + (ron + rl) / r);
export function mBoostLossy(d, r, ron, rl) { const dp = 1 - d; return (1 / dp) / (1 + (ron + rl) / (dp * dp * r)); }
export function mBuckBoostLossy(d, r, ron, rl) { const dp = 1 - d; return (d / dp) / (1 + (ron + rl) / (dp * dp * r)); }

export function averageOverPeriod(values, durations) {
  const T = durations.reduce((a, b) => a + b, 0);
  let s = 0;
  for (let i = 0; i < values.length; i++) s += values[i] * durations[i];
  return s / T;
}

export const kParam = (l, r, fs) => (2 * l * fs) / r;
export function kCrit(top, d) {
  if (top === 'buck') return 1 - d;
  if (top === 'boost') return d * (1 - d) ** 2;
  if (top === 'buck_boost') return (1 - d) ** 2;
  throw new Error(top);
}
export function mDcm(top, d, l, r, fs) {
  const k = kParam(l, r, fs);
  if (top === 'buck') return 2 / (1 + Math.sqrt(1 + (4 * k) / (d * d)));
  if (top === 'boost') return (1 + Math.sqrt(1 + (4 * d * d) / k)) / 2;
  if (top === 'buck_boost') return -d / Math.sqrt(k);
  throw new Error(top);
}

export function inductorForRipple(top, vin, vout, d, di, fs) {
  vout = Math.abs(vout);
  if (top === 'buck' || top === 'sync_buck') return ((vin - vout) * d) / (di * fs);
  return (vin * d) / (di * fs);
}
export function outputCapForRipple(top, iout, d, di, dv, fs) {
  if (top === 'buck' || top === 'sync_buck') return di / (8 * fs * dv);
  return (iout * d) / (fs * dv);
}

// ------------------------------------------------------------------ losses
export const conduction = (irms, r) => irms * irms * r;
export const rmsTrapezoid = (iavg, di, d) => Math.sqrt(d * (iavg * iavg + (di * di) / 12));
export const overlap = (v, i, ton, toff, fs) => 0.5 * v * Math.abs(i) * (ton + toff) * fs;
export const cossLinear = (c, v, fs) => 0.5 * c * v * v * fs;
export const qossAt = (qref, vref, v, m) => (v <= 0 ? 0 : qref * Math.pow(v / vref, m));
export const eossFromQoss = (q, v, m) => (m / (m + 1)) * q * v;
export const hardTurnOnHalfbridge = (q, v, fs) => q * v * fs;
export const reverseRecovery = (qrr, v, fs) => qrr * v * fs;
export const gateDrive = (qg, vdrv, fs) => qg * vdrv * fs;
export const deadTime = (vsd, i, td, fs, n = 2) => vsd * Math.abs(i) * td * fs * n;
export function zvsResidualFraction(i, td, qoss) {
  if (qoss <= 0) return 0;
  return Math.max(0, 1 - (Math.abs(i) * td) / (2 * qoss));
}
export function overlapTime(qsw, vdrv, vpl, rg, turnOn = true) {
  const ig = turnOn ? (vdrv - vpl) / rg : vpl / rg;
  return qsw / ig;
}

// ------------------------------------------------------------------ magnetics
export const MATERIALS = {
  ferrite_generic: { alpha: 1.46, beta: 2.75, anchor_f: 100e3, anchor_b: 0.1, anchor_pv: 300e3, label: 'Generic MnZn power ferrite (illustrative)' },
  powder_generic: { alpha: 1.3, beta: 2.2, anchor_f: 100e3, anchor_b: 0.1, anchor_pv: 1.2e6, label: 'Generic composite / powder core (illustrative)' },
};
export const steinmetzK = (m) => m.anchor_pv / (Math.pow(m.anchor_f, m.alpha) * Math.pow(m.anchor_b, m.beta));
export const steinmetz = (k, a, b, f, bpk) => k * Math.pow(f, a) * Math.pow(bpk, b);

// Lanczos approximation (g = 7, n = 9): ~15 significant digits for x > 0
const LG = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
  -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
export function gamma(x) {
  if (x < 0.5) return Math.PI / (Math.sin(Math.PI * x) * gamma(1 - x));
  x -= 1;
  let a = LG[0];
  const t = x + 7.5;
  for (let i = 1; i < 9; i++) a += LG[i] / (x + i);
  return Math.sqrt(2 * Math.PI) * Math.pow(t, x + 0.5) * Math.exp(-t) * a;
}
const cosIntegral = (a) => (2 * Math.sqrt(Math.PI) * gamma((a + 1) / 2)) / gamma(a / 2 + 1);
export const igseKi = (k, a, b) => k / (Math.pow(2 * Math.PI, a - 1) * cosIntegral(a) * Math.pow(2, b - a));
export function igseTriangular(k, a, b, f, db, duty) {
  const ki = igseKi(k, a, b);
  const d = Math.min(Math.max(duty, 1e-9), 1 - 1e-9);
  return ki * Math.pow(db, b) * Math.pow(f, a) * (Math.pow(d, 1 - a) + Math.pow(1 - d, 1 - a));
}
export function igsePiecewiseLinear(k, a, b, times, flux) {
  const T = times[times.length - 1] - times[0];
  let mx = -Infinity, mn = Infinity;
  for (const x of flux) { if (x > mx) mx = x; if (x < mn) mn = x; }
  const dbpp = mx - mn;
  if (dbpp <= 0 || T <= 0) return 0;
  const ki = igseKi(k, a, b);
  let acc = 0;
  for (let i = 0; i < times.length - 1; i++) {
    const tau = times[i + 1] - times[i];
    if (tau <= 0) continue;
    acc += Math.pow(Math.abs(flux[i + 1] - flux[i]) / tau, a) * tau;
  }
  return (ki * Math.pow(dbpp, b - a) * acc) / T;
}

// ------------------------------------------------------------------ switched capacitor
export const rSsl = (ac, caps, f) => ac.reduce((s, a, i) => s + (a * a) / (caps[i] * f), 0);
export const rFsl = (ar, rs) => 2 * ar.reduce((s, a, i) => s + rs[i] * a * a, 0);
export const rOut = (ac, caps, f, ar, rs) => Math.hypot(rSsl(ac, caps, f), rFsl(ar, rs));
export function simulateSeriesParallel(vin, vout, c, r, f) {
  const T = 1 / f, tau = 2 * r * c, a = Math.exp(-(T / 2) / tau);
  const t1 = vin - vout, t2 = vout;
  const v0 = (t2 * (1 - a) + t1 * a * (1 - a)) / (1 - a * a);
  const v1 = t1 + (v0 - t1) * a;
  const q = c * (v1 - v0);
  const iout = (2 * q) / T;
  const ploss = (vin * q - vout * 2 * q) / T;
  return { i_out: iout, r_out: (vin / 2 - vout) / iout, p_loss: ploss, v_c_min: v0, v_c_max: v1 };
}

// ------------------------------------------------------------------ efficiency
export const CEC_WEIGHTS = [[0.1, 0.04], [0.2, 0.05], [0.3, 0.12], [0.5, 0.21], [0.75, 0.53], [1.0, 0.05]];
export const EURO_WEIGHTS = [[0.05, 0.03], [0.1, 0.06], [0.2, 0.13], [0.3, 0.1], [0.5, 0.48], [1.0, 0.2]];
export const efficiency = (pout, total) => pout / (pout + total);
export const weighted = (etaAt, w) => w.reduce((s, [f, x]) => s + x * etaAt(f), 0);
