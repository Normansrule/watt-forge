// fundamentals.js -- volt-second balance and CCM/DCM widgets.
import * as C from '../model/core.js';
import { lineChart } from '../ui/charts.js';
import { $, slider } from '../ui/ui.js';

// ---- volt-second balance (buck with a stiff output)
const st = { vin: 48, vout: 12, d: 0.35 };
function vs() {
  const { vin, vout, d } = st;
  const L = 15e-6, fs = 200e3, Ts = 1 / fs;
  const von = vin - vout, voff = -vout;
  const res = C.averageOverPeriod([von, voff], [d, 1 - d]);
  const dbal = vout / vin;
  $('#vs-res').textContent = (res * Ts * 1e6).toFixed(2) + ' V-us';
  $('#vs-dbal').textContent = dbal.toFixed(3);
  $('#vs-msg').textContent = Math.abs(d - dbal) < 0.006
    ? 'Balanced: the current returns to its starting value every period (steady state).'
    : `Unbalanced: each period the current ${res > 0 ? 'grows' : 'falls'} by ${(Math.abs(res) * Ts / L).toFixed(2)} A, so it ratchets away until Vout or D changes.`;
  const periods = 4, n = 200;
  const vl = [], il = [];
  let i = 0;
  for (let k = 0; k <= periods * n; k++) {
    const t = k / n, ph = t % 1;
    const v = ph < d ? von : voff;
    vl.push([t, v]);
    il.push([t, i]);
    i += (v / L) * (Ts / n);
  }
  lineChart($('#vs-vl'), { height: 190, title: 'Inductor voltage v_L', series: [{ name: 'v_L', cls: 'c1', pts: vl, endDot: false }],
    x: { label: 'time [periods]', min: 0, max: periods }, y: { label: 'V', min: Math.min(voff, -1) * 1.1, max: Math.max(von, 1) * 1.1 },
    zones: [], tipFmt: (y) => y.toFixed(1) + ' V' });
  lineChart($('#vs-il'), { height: 190, title: 'Inductor current (starting from 0 A)', series: [{ name: 'i_L', cls: 'c2', pts: il, endDot: false }],
    x: { label: 'time [periods]', min: 0, max: periods }, y: { label: 'A' }, tipFmt: (y) => y.toFixed(2) + ' A' });
}
slider('vs-vin', (v) => v + ' V', (v) => { st.vin = v; vs(); });
slider('vs-vout', (v) => v + ' V', (v) => { st.vout = v; vs(); });
slider('vs-d', (v) => v.toFixed(2), (v) => { st.d = v; vs(); });

// ---- CCM / DCM map
const k = { top: 'buck', l: 15e-6, r: 5, d: 0.4 };
function kmap() {
  const fs = 200e3;
  const K = C.kParam(k.l, k.r, fs);
  const pts = [];
  for (let d = 0.01; d <= 0.99; d += 0.01) pts.push([d, C.kCrit(k.top, d)]);
  const ccm = K > C.kCrit(k.top, k.d);
  const ideal = { buck: C.mBuck, boost: C.mBoost, buck_boost: C.mBuckBoost }[k.top](k.d);
  const m = ccm ? ideal : C.mDcm(k.top, k.d, k.l, k.r, fs);
  $('#k-mode').textContent = ccm ? 'CCM' : 'DCM';
  $('#k-m').textContent = Math.abs(m).toFixed(3) + (ccm ? '' : ` (CCM would give ${Math.abs(ideal).toFixed(3)})`);
  lineChart($('#k-chart'), { height: 300, title: 'K_crit(D): below the curve the diode converter is in DCM',
    series: [{ name: 'K_crit', cls: 'c1', pts, endDot: false }], x: { label: 'duty cycle D', min: 0, max: 1 },
    y: { label: 'K', min: 0, max: Math.max(1.05, K * 1.1) }, marks: [{ x: k.d, y: K, cls: ccm ? 'c3' : 'c2', label: `K = ${K.toFixed(3)}` }],
    tipFmt: (y) => y.toFixed(3) });
}
$('#k-top').addEventListener('change', (e) => { k.top = e.target.value; kmap(); });
slider('k-l', (v) => v + ' uH', (v) => { k.l = v * 1e-6; kmap(); });
slider('k-r', (v) => v + ' ohm', (v) => { k.r = v; kmap(); });
slider('k-d', (v) => v.toFixed(2), (v) => { k.d = v; kmap(); });
