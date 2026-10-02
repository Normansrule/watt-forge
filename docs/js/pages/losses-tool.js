// losses-tool.js -- live loss budget for a user-defined transistor.
import { design } from '../model/topologies.js';
import { switching, get } from '../model/devices.js';
import { donut, barList, lineChart } from '../ui/charts.js';
import { $, h, slider, pct, groupLosses, LOSS_NAMES, debounce } from '../ui/ui.js';

const SPECS = { buck: { vin: 48, vout: 12 }, boost: { vin: 24, vout: 48 }, four_switch: { vin: 36, vout: 48 } };
const st = { top: 'buck', rds: 1.8, qoss: 85, qg: 23, qrr: 0, f: 300e3, load: 150, base: 'EPC2302' };
const pre = $('#lx-preset');
for (const d of switching()) pre.append(h('option', { value: d.id, text: `${d.id} (${d.tech})` }));
pre.value = st.base;

function device() {
  const b = get(st.base);
  // a custom device derived from the preset with the slider values
  return { ...b, id: 'custom', rds_max_mohm: st.rds, rds_typ_mohm: st.rds * 0.8, qoss_nc: st.qoss, qoss_v: 50, qg_nc: st.qg,
    qgd_nc: st.qg / 8, qrr_nc: st.qrr, vdrv: 5, vpl: 2.6, rg_ohm: 1.6, vsd: b.tech === 'Si' ? 0.85 : 2.0, qoss_exp: 0.6, verified: [] };
}
function spec(fs, pout) { return { topology: st.top, ...SPECS[st.top], pout, fs, device: device(), sync: true, t_dead: 15e-9 }; }

const run = debounce(() => {
  const r = design(spec(st.f, st.load));
  $('#lx-eta').textContent = pct(r.eta);
  $('#lx-loss').textContent = r.total_loss.toFixed(2) + ' W';
  const items = Object.entries(r.losses).map(([k, v]) => ({ name: LOSS_NAMES[k] || k, value: v, cls: 'c1' })).sort((a, b) => b.value - a.value);
  $('#lx-top-term').textContent = items[0].name;
  donut($('#lx-donut'), groupLosses(r.losses), { center: r.total_loss.toFixed(2) + ' W', sub: 'total loss' });
  barList($('#lx-bars'), items);
  const pts = [];
  for (let f = 25e3; f <= 2e6; f *= 1.12) pts.push([f / 1e3, 100 * design(spec(f, st.load)).eta]);
  const best = pts.reduce((a, b) => (b[1] > a[1] ? b : a));
  lineChart($('#lx-fcurve'), { height: 230, title: 'Efficiency vs switching frequency (same load)', series: [{ name: 'efficiency', cls: 'c1', pts, endDot: false }],
    x: { label: 'kHz', log: true, min: 25, max: 2000, fmt: (v) => String(Math.round(v)) }, y: { label: '%' },
    marks: [{ x: st.f / 1e3, y: 100 * r.eta, cls: 'c2', label: 'now' }, { x: best[0], y: best[1], cls: 'c3', label: `best ~${best[0].toFixed(0)} kHz` }],
    tipFmt: (y) => y.toFixed(2) + ' %' });
}, 25);

const sl = {
  rds: slider('lx-rds', (v) => v.toFixed(1) + ' mOhm', (v) => { st.rds = v; run(); }),
  qoss: slider('lx-qoss', (v) => v + ' nC', (v) => { st.qoss = v; run(); }),
  qg: slider('lx-qg', (v) => v + ' nC', (v) => { st.qg = v; run(); }),
  qrr: slider('lx-qrr', (v) => v + ' nC', (v) => { st.qrr = v; run(); }),
};
slider('lx-f', (v) => v + ' kHz', (v) => { st.f = v * 1e3; run(); });
slider('lx-load', (v) => v + ' W', (v) => { st.load = v; run(); });
$('#lx-top').addEventListener('change', (e) => { st.top = e.target.value; run(); });
pre.addEventListener('change', () => {
  st.base = pre.value;
  const d = get(st.base);
  const q50 = d.qoss_nc * Math.pow(50 / d.qoss_v, d.qoss_exp);
  for (const [id, v] of [['lx-rds', d.rds_max_mohm], ['lx-qoss', Math.round(q50)], ['lx-qg', d.qg_nc], ['lx-qrr', d.qrr_nc]]) {
    const el = $('#' + id);
    el.value = v;
    el.dispatchEvent(new Event('input'));
  }
});
void sl;
run();
