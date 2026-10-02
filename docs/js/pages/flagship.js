// flagship.js -- operating-point explorer, efficiency curves, weighted efficiency, BOM.
import * as F from '../model/flagship.js';
import * as C from '../model/core.js';
import { BOM } from '../data/bom.js';
import { donut, barList, lineChart } from '../ui/charts.js';
import { $, h, slider, pct, groupLosses, LOSS_NAMES, debounce, wireRepoLinks } from '../ui/ui.js';

const p = F.defaultParams();
const st = { vin: 56, vout: 48, load: 1 };

const op = debounce(() => {
  const pout = st.load * Math.min(p.spec.p_max, 0.97 * p.spec.iin_max * st.vin);
  const r = F.best(st.vin, st.vout, pout, p);
  $('#fx-eta').textContent = pct(r.eta);
  $('#fx-mode').textContent = r.label.replace('buckboost', 'buck-boost');
  $('#fx-fs').textContent = (r.fs / 1e3).toFixed(0) + ' kHz';
  $('#fx-d').textContent = `${r.d1.toFixed(3)} / ${r.d2.toFixed(3)}`;
  $('#fx-il').textContent = `${r.il.toFixed(2)} A / ${r.ripple_pp.toFixed(2)} A`;
  $('#fx-hard').textContent = `${r.n_hard} of ${r.waveform.edges.length}`;
  $('#fx-p').textContent = pout.toFixed(0) + ' W';
  const nearBp = Math.abs(st.vin - st.vout) / st.vout < 0.02;
  $('#fx-bypass').textContent = nearBp ? `In bypass (if the panel's MPP is here) the model predicts ${pct(F.bypass(st.vout, pout, p).eta)}.` : '';
  donut($('#fx-donut'), groupLosses(r.losses), { center: r.loss_total.toFixed(2) + ' W', sub: 'total loss' });
  barList($('#fx-bars'), Object.entries(r.losses).map(([k, v]) => ({ name: LOSS_NAMES[k] || k, value: v, cls: 'c1' })).sort((a, b) => b.value - a.value));
  const w = r.waveform;
  const pts = [];
  for (let per = 0; per < 2; per++) w.segs.forEach((s, k) => { pts.push([(per * w.T + s.t0) * 1e6, r.il + w.knots[k]]); });
  pts.push([2 * w.T * 1e6, r.il + w.knots[0]]);
  lineChart($('#fx-wave'), { height: 200, title: 'Inductor current over two switching periods (ideal waveform)', series: [{ name: 'i_L', cls: 'c2', pts, endDot: false }],
    x: { label: 'time [us]', min: 0, max: 2 * w.T * 1e6 }, y: { label: 'A', min: Math.min(0, ...pts.map((q) => q[1])) * 1.1, max: Math.max(...pts.map((q) => q[1])) * 1.1 + 0.1 },
    tipFmt: (y) => y.toFixed(2) + ' A' });
}, 25);
slider('fx-vin', (v) => v.toFixed(1) + ' V', (v) => { st.vin = v; op(); });
slider('fx-vout', (v) => v.toFixed(1) + ' V', (v) => { st.vout = v; op(); });
slider('fx-load', (v) => v + ' %', (v) => { st.load = v / 100; op(); });

// efficiency vs Vin, computed live from the same model
setTimeout(() => {
  const vins = [];
  for (let v = 12; v <= 60; v += 2) vins.push(v);
  const loads = [[0.1, 'c1', '10 %'], [0.3, 'c2', '30 %'], [0.5, 'c3', '50 %'], [1.0, 'c4', '100 %']];
  const series = loads.map(([f, cls, name]) => ({ name, cls, pts: vins.map((v) => [v, 100 * F.best(v, 48, f * F.pRated(p, v), p).eta]) }));
  lineChart($('#fx-curve'), { height: 320, title: 'Predicted efficiency vs panel voltage (48 V out, includes housekeeping)', series,
    x: { label: 'panel voltage [V]', min: 12, max: 60 }, y: { label: '%', min: 94.5, max: 100 },
    zones: [{ x0: 22, x1: 26, label: 'SC 1:2' }, { x0: 47.5, x1: 48.5, label: 'both legs' }], tipFmt: (y) => y.toFixed(2) + ' %' });
  const tb = $('#fx-weighted tbody');
  for (const v of [12, 24, 36, 48, 56, 60]) {
    const cache = new Map();
    const at = (f) => { if (!cache.has(f)) cache.set(f, F.best(v, 48, f * F.pRated(p, v), p).eta); return cache.get(f); };
    const peak = Math.max(...[0.2, 0.3, 0.5, 0.75, 1].map(at));
    tb.append(h('tr', {}, h('td', { class: 'r', text: v + ' V' }), h('td', { class: 'r', text: pct(C.weighted(at, C.CEC_WEIGHTS)) }),
      h('td', { class: 'r', text: pct(C.weighted(at, C.EURO_WEIGHTS)) }), h('td', { class: 'r', text: pct(peak) })));
  }
}, 30);

const bom = $('#fx-bom tbody');
for (const b of BOM) {
  bom.append(h('tr', {}, h('td', { text: b.ref }), h('td', { class: 'r', text: b.qty }),
    h('td', {}, b.source && b.source.startsWith('https://') ? h('a', { href: b.source, rel: 'noopener noreferrer', text: b.part_number }) : b.part_number,
      h('div', { class: 'note', text: b.manufacturer })),
    h('td', { text: `${b.description}. ${b.key_parameters}` }), h('td', {}, h('span', { class: 'pill' + (b.status.startsWith('VERIFIED') ? '' : ' warn'), text: b.status }))));
}
wireRepoLinks();
