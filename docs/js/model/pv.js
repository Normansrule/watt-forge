// pv.js -- single-diode PV panel with bypass-diode substrings. Port of watt_forge/pv.py.
const K_B = 1.380649e-23, Q_E = 1.602176634e-19;

export function defaultPanel() {
  return { isc_stc: 10.4, voc_stc: 49.5, n_cells: 72, n_sub: 3, ideality: 1.3, rs_total: 0.3, rsh_total: 450,
    beta_voc: -0.0029, alpha_isc: 0.0005, v_bypass: 0.4, n_series: 1 };
}

function subParams(p, g, tc) {
  const ns = Math.floor(p.n_cells / p.n_sub);
  const vt = (K_B * (tc + 273.15)) / Q_E;
  const a = p.ideality * ns * vt;
  const rs = p.rs_total / p.n_sub, rsh = p.rsh_total / p.n_sub;
  const vocSub = (p.voc_stc / p.n_sub) * (1 + p.beta_voc * (tc - 25));
  const iscT = p.isc_stc * (1 + p.alpha_isc * (tc - 25));
  const i0 = (iscT - vocSub / rsh) / (Math.exp(vocSub / a) - 1);
  const iph = ((iscT * Math.max(g, 0)) / 1000) * (1 + rs / rsh);
  return [iph, i0, a, rs, rsh, vocSub];
}
function resid(v, i, iph, i0, a, rs, rsh) {
  const x = Math.min((v + i * rs) / a, 200);
  return iph - i0 * (Math.exp(x) - 1) - (v + i * rs) / rsh - i;
}

export function substringVoltage(i, g, tc, p, iters = 40) {
  const [iph, i0, a, rs, rsh, voc] = subParams(p, g, tc);
  if (resid(-p.v_bypass, i, iph, i0, a, rs, rsh) < 0) return -p.v_bypass;
  let v = voc * 1.1 + 1;
  for (let k = 0; k < iters; k++) {
    const x = Math.min((v + i * rs) / a, 200);
    const e = Math.exp(x);
    const gv = iph - i0 * (e - 1) - (v + i * rs) / rsh - i;
    const dg = (-i0 * e) / a - 1 / rsh;
    const step = gv / dg;
    v -= step;
    if (step > -1e-12 && step < 1e-12) break;
  }
  return v;
}

export function panelVoltage(i, irr, tc, p) {
  let v = 0;
  for (const g of irr) v += substringVoltage(i, g, tc, p);
  return v * p.n_series;
}

export function panelCurrent(v, irr, tc, p, iters = 50) {
  const iMax = p.isc_stc * 1.3 * Math.max(1, Math.max(...irr) / 1000);
  if (v <= panelVoltage(iMax, irr, tc, p)) return iMax;
  let lo = 0, hi = iMax;
  if (v >= panelVoltage(0, irr, tc, p)) return 0;
  for (let k = 0; k < iters; k++) {
    const mid = 0.5 * (lo + hi);
    if (panelVoltage(mid, irr, tc, p) > v) lo = mid; else hi = mid;
  }
  return 0.5 * (lo + hi);
}

export function pvCurve(irr, tc, p, n = 120) {
  const iTop = (Math.max(...irr) / 1000) * p.isc_stc * (1 + p.alpha_isc * (tc - 25)) * 1.02;
  const pts = [];
  for (let k = 0; k <= n; k++) {
    const i = (iTop * k) / n;
    const v = panelVoltage(i, irr, tc, p);
    if (v < 0) continue;
    pts.push({ v, i, p: v * i });
  }
  pts.sort((a, b) => a.v - b.v);
  return pts;
}

export function globalMpp(irr, tc, p, n = 200) {
  const pts = pvCurve(irr, tc, p, n);
  const best = pts.reduce((a, b) => (b.p > a.p ? b : a));
  const step = (Math.max(...pts.map((d) => d.i)) || 1) / n;
  let lo = Math.max(0, best.i - step), hi = best.i + step;
  const gr = (Math.sqrt(5) - 1) / 2;
  const f = (i) => i * panelVoltage(i, irr, tc, p);
  let c = hi - gr * (hi - lo), d = lo + gr * (hi - lo);
  for (let k = 0; k < 40; k++) {
    if (f(c) > f(d)) hi = d; else lo = c;
    c = hi - gr * (hi - lo); d = lo + gr * (hi - lo);
  }
  const i = 0.5 * (lo + hi);
  const v = panelVoltage(i, irr, tc, p);
  return { v, i, p: v * i };
}
