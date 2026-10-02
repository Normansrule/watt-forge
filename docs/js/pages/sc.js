// sc.js -- switched-capacitor limits and the three-level ripple comparison.
import * as C from '../model/core.js';
import * as F from '../model/flagship.js';
import { lineChart } from '../ui/charts.js';
import { $, slider, eng } from '../ui/ui.js';

const st = { c: 10e-6, r: 10e-3, f: 1e5 };
function scDraw() {
  const pts = [], ssl = [], fsl = [];
  for (let e = 3; e <= 8.001; e += 0.05) {
    const f = Math.pow(10, e);
    pts.push([f, C.simulateSeriesParallel(48, 23.5, st.c, st.r, f).r_out]);
    ssl.push([f, C.rSsl([0.5], [st.c], f)]);
    fsl.push([f, C.rFsl([0.5, 0.5, 0.5, 0.5], [st.r, st.r, st.r, st.r])]);
  }
  const ex = C.simulateSeriesParallel(48, 23.5, st.c, st.r, st.f).r_out;
  const s = C.rSsl([0.5], [st.c], st.f), q = C.rFsl([0.5, 0.5, 0.5, 0.5], [st.r, st.r, st.r, st.r]);
  $('#sc-rout').textContent = eng(ex, 'ohm');
  $('#sc-loss').textContent = (4 * ex).toFixed(3) + ' W';
  $('#sc-reg').textContent = s > 3 * q ? 'slow-switching' : q > 3 * s ? 'fast-switching' : 'transition';
  lineChart($('#sc-chart'), { height: 300, title: '2:1 series-parallel: output resistance vs frequency',
    series: [{ name: 'exact', cls: 'c1', pts, endDot: false }, { name: 'SSL 1/(4Cf)', cls: 'c2', pts: ssl, endDot: false }, { name: 'FSL 2R', cls: 'c3', pts: fsl, endDot: false }],
    x: { label: 'frequency [Hz]', log: true, min: 1e3, max: 1e8, fmt: (v) => eng(v, 'Hz', 2) },
    y: { label: 'R_out [ohm]', log: true, min: Math.min(q, 1e-3) * 0.5, max: Math.max(...ssl.map((p) => p[1])) * 1.2, fmt: (v) => eng(v, '', 2) },
    marks: [{ x: st.f, y: ex, cls: 'c1' }], tipFmt: (y) => eng(y, 'ohm') });
}
slider('sc-c', (v) => v + ' uF', (v) => { st.c = v * 1e-6; scDraw(); });
slider('sc-r', (v) => v + ' mOhm', (v) => { st.r = v * 1e-3; scDraw(); });
slider('sc-f', (v) => eng(Math.pow(10, v), 'Hz'), (v) => { st.f = Math.pow(10, v); scDraw(); });

// ---- three-level vs two-level ripple
function ripple3(d) {
  const fs = 100e3, T = 1 / fs, vin = 60, vout = d * vin;
  const { segs, edges } = F.build(d, 0, 0, T, true, false);
  const w = F.idealRipple(vin, vout, 4.7e-6, segs, edges, T);
  return Math.max(...w.knots) - Math.min(...w.knots);
}
const ripple2 = (d) => (60 * d * (1 - d)) / (4.7e-6 * 100e3);
let hd = 0.45;
function hDraw() {
  const p3 = [], p2 = [];
  for (let d = 0.02; d <= 0.981; d += 0.01) { p3.push([d, ripple3(d)]); p2.push([d, ripple2(d)]); }
  $('#h-r3').textContent = ripple3(hd).toFixed(2) + ' A';
  $('#h-r2').textContent = ripple2(hd).toFixed(2) + ' A';
  lineChart($('#h-chart'), { height: 300, title: 'Inductor ripple: three-level leg vs two-level half-bridge',
    series: [{ name: 'two-level', cls: 'c2', pts: p2, endDot: false }, { name: 'three-level', cls: 'c1', pts: p3, endDot: false }],
    x: { label: 'duty cycle D', min: 0, max: 1 }, y: { label: 'ripple [A pk-pk]', min: 0 },
    marks: [{ x: hd, y: ripple3(hd), cls: 'c1', label: hd === 0.5 ? 'soft-charged SC point' : '' }], tipFmt: (y) => y.toFixed(2) + ' A' });
}
slider('h-d', (v) => v.toFixed(2), (v) => { hd = v; hDraw(); });
