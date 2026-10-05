// control-lesson.js -- interactive PV curve with global and local maxima.
import * as PV from '../model/pv.js';
import { lineChart } from '../ui/charts.js';
import { $, h, slider, debounce } from '../ui/ui.js';
import { CONTROL_BENCHMARK as B } from '../data/control_benchmark.js';
import { REFERENCES } from '../data/references.js';

const panel = PV.defaultPanel();
const st = { g: 1000, t: 25, s: 1 };
const run = debounce(() => {
  const irr = [st.g, st.g, st.g * st.s];
  const pts = PV.pvCurve(irr, st.t, panel, 260);
  const curve = pts.map((p) => [p.v, p.p]);
  const mpp = PV.globalMpp(irr, st.t, panel);
  const peaks = [];
  for (let i = 1; i < pts.length - 1; i++) if (pts[i].p > pts[i - 1].p && pts[i].p >= pts[i + 1].p && pts[i].p > 2) peaks.push(pts[i]);
  const voc = PV.panelVoltage(0, irr, st.t, panel);
  $('#pv-mpp').textContent = `${mpp.p.toFixed(0)} W at ${mpp.v.toFixed(1)} V`;
  $('#pv-voc').textContent = voc.toFixed(1) + ' V';
  $('#pv-n').textContent = String(peaks.length);
  const marks = peaks.filter((p) => Math.abs(p.v - mpp.v) > 1).map((p) => ({ x: p.v, y: p.p, cls: 'c2', label: 'local' }));
  marks.push({ x: mpp.v, y: mpp.p, cls: 'c3', label: 'global MPP' });
  lineChart($('#pv-chart'), { height: 320, title: 'Panel power vs voltage', series: [{ name: 'P', cls: 'c1', pts: curve, endDot: false }],
    x: { label: 'panel voltage [V]', min: 0, max: Math.max(52, voc + 1) }, y: { label: 'power [W]', min: 0, max: 450 }, marks,
    tipFmt: (y) => y.toFixed(1) + ' W' });
}, 15);
slider('pv-g', (v) => v + ' W/m^2', (v) => { st.g = v; run(); });
slider('pv-t', (v) => v + ' C', (v) => { st.t = v; run(); });
slider('pv-s', (v) => v + ' %', (v) => { st.s = v / 100; run(); });

// ---- benchmark numbers and references, filled from the generated data so text and data never drift

const pc = (x) => `${(100 * x).toFixed(2)} %`;
for (const el of document.querySelectorAll('.benchline[data-key]')) {
  const k = el.dataset.key;
  const r = B.results;
  el.append(h('span', { class: 'pill', text: B.algorithms[k].name }), ' ',
    `EN 50530-style 30-100 %: ${pc(r.en50530_high[k].eta_mppt)}, clouds: ${pc(r.clouds[k].eta_mppt)}, partial shading: ${pc(r.shading[k].eta_mppt)}.`);
}
const tb = document.querySelector('#cmp-table tbody');
for (const k of Object.keys(B.algorithms).sort((a, b) => B.overall[b].eta_mppt - B.overall[a].eta_mppt)) {
  const r = B.results;
  tb.append(h('tr', {}, h('td', { text: B.algorithms[k].name }), h('td', { text: B.algorithms[k].family }),
    h('td', { class: 'r', text: pc(r.en50530_high[k].eta_mppt) }), h('td', { class: 'r', text: pc(r.clouds[k].eta_mppt) }),
    h('td', { class: 'r', text: pc(r.shading[k].eta_mppt) }), h('td', { class: 'r', text: pc(B.overall[k].eta_mppt) })));
}
const ul = document.getElementById('ctl-refs');
for (const ref of REFERENCES.references.filter((x) => x.category === 'MPPT and control' || x.category === 'Efficiency control' || x.id === 'en50530')) {
  const link = ref.doi ? h('a', { href: `https://doi.org/${ref.doi}`, text: `doi:${ref.doi}` }) : h('a', { href: ref.url, text: 'source' });
  ul.append(h('li', {}, `${ref.authors}, "${ref.title}," ${ref.venue}, ${ref.year}. `, link));
}
