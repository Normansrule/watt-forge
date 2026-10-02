// validator.js -- check a design's efficiency curve against a user target.
import * as F from '../model/flagship.js';
import * as C from '../model/core.js';
import { design } from '../model/topologies.js';
import { compile } from '../model/expr.js';
import { lineChart } from '../ui/charts.js';
import { $, h, slider, pct, store, groupLosses, debounce } from '../ui/ui.js';
import { validateDesign } from './designer-schema.js';

const p = F.defaultParams();
const st = { src: 'flagship', vin: 36 };
const HINTS = {
  'Switch conduction': 'lower R_ds(on), parallel devices, or reduce RMS current (lower ripple)',
  Switching: 'lower the switching frequency, shorten dead time, or get zero-voltage switching (more ripple at light load)',
  Inductor: 'lower-DCR inductor; if it is core loss, lower ripple or a lower-loss material',
  Capacitors: 'more parallel capacitors (lower ESR) or lower ripple current',
  'Sense, copper, disconnect': 'smaller shunts, wider copper, or paralleled disconnect switches',
  Housekeeping: 'fixed power dominates at light load: lower-power controller and drivers, or burst mode',
};

function savedDesigns() { return store.get('designs', {}); }
function refreshSaved() {
  const sel = $('#va-saved');
  sel.textContent = '';
  const all = savedDesigns();
  if (!Object.keys(all).length) sel.append(h('option', { value: '', text: 'No saved designs yet: save one in the topology designer' }));
  for (const k of Object.keys(all)) sel.append(h('option', { value: k, text: k }));
}

function evalAt(frac) {
  if (st.src === 'flagship') {
    const r = F.best(st.vin, 48, frac * F.pRated(p, st.vin), p);
    return { eta: r.eta, losses: r.losses };
  }
  const d = validateDesign(savedDesigns()[$('#va-saved').value]);
  const r = design({ topology: d.topology, vin: d.vin, vout: d.vout, pout: d.pout * frac, fs: d.fs_khz * 1e3, ripple_frac: d.ripple_frac,
    device: d.device, sync: d.sync, dcr_mohm: d.dcr_mohm, n: d.n });
  return { eta: r.eta, losses: r.losses };
}

function targetFn() {
  if ($('#va-mode').value === 'formula') {
    const f = compile($('#va-formula').value, ['p']);
    return (frac) => f({ p: frac });
  }
  const rows = $('#va-table').value.split('\n').map((l) => l.trim()).filter(Boolean);
  if (rows.length > 50) throw new Error('Use at most 50 target points.');
  const pts = rows.map((l, i) => {
    const m = /^(\d+(?:\.\d+)?)\s*[,;\s]\s*(\d+(?:\.\d+)?)$/.exec(l);
    if (!m) throw new Error(`Line ${i + 1}: write "load %, efficiency %", for example "50, 98.5".`);
    return [+m[1] / 100, +m[2] / 100];
  }).sort((a, b) => a[0] - b[0]);
  if (pts.some(([x, y]) => x <= 0 || x > 1.5 || y <= 0 || y >= 1)) throw new Error('Loads must be 1-150 % and efficiencies between 0 and 100 %.');
  return (frac) => {
    if (frac <= pts[0][0]) return pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) if (frac <= pts[i + 1][0]) {
      const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
      return y0 + ((y1 - y0) * (frac - x0)) / (x1 - x0);
    }
    return pts[pts.length - 1][1];
  };
}

const run = debounce(() => {
  $('#va-err').textContent = '';
  let tgt;
  try { tgt = targetFn(); } catch (e) { $('#va-err').textContent = e.message; return; }
  if (st.src === 'saved' && !savedDesigns()[$('#va-saved').value]) { $('#va-err').textContent = 'No saved design selected. Save one in the topology designer first.'; return; }
  const loads = [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0];
  const rows = [];
  try {
    for (const f of loads) {
      const r = evalAt(f);
      const t = tgt(f);
      if (!isFinite(t)) throw new Error('The target formula gives a non-number at p = ' + f);
      const groups = groupLosses(r.losses).sort((a, b) => b.value - a.value);
      rows.push({ f, eta: r.eta, t, margin: r.eta - t, top: groups[0] });
    }
  } catch (e) { $('#va-err').textContent = e.message; return; }
  const fails = rows.filter((r) => r.margin < 0);
  $('#va-verdict').textContent = fails.length ? `Misses ${fails.length} of ${rows.length}` : 'Meets target';
  const worst = rows.reduce((a, b) => (b.margin < a.margin ? b : a));
  $('#va-worst').textContent = worst.margin < 0 ? `${(100 * worst.margin).toFixed(2)} pts at ${(100 * worst.f).toFixed(0)} %` : 'none';
  const at = (frac) => evalAt(frac).eta;
  $('#va-cec').textContent = pct(C.weighted(at, C.CEC_WEIGHTS));
  $('#va-euro').textContent = pct(C.weighted(at, C.EURO_WEIGHTS));
  lineChart($('#va-chart'), { height: 280, title: 'Design vs target', series: [{ name: 'design', cls: 'c1', pts: rows.map((r) => [100 * r.f, 100 * r.eta]) }],
    target: rows.map((r) => [100 * r.f, 100 * r.t]), legend: true,
    marks: fails.map((r) => ({ x: 100 * r.f, y: 100 * r.eta, cls: 'c2' })), x: { label: 'load [%]', min: 0, max: 100 },
    y: { label: 'efficiency [%]', min: Math.min(...rows.map((r) => 100 * Math.min(r.eta, r.t))) - 0.3, max: 100 }, tipFmt: (y) => y.toFixed(2) + ' %' });
  const tb = $('#va-tab tbody');
  tb.textContent = '';
  for (const r of rows) {
    tb.append(h('tr', {}, h('td', { class: 'r', text: (100 * r.f).toFixed(0) + ' %' }), h('td', { class: 'r', text: pct(r.eta) }),
      h('td', { class: 'r', text: pct(r.t) }), h('td', { class: 'r', text: (r.margin >= 0 ? '+' : '') + (100 * r.margin).toFixed(2) + ' pts' }),
      h('td', { text: r.margin < 0 ? `${r.top.name} (${r.top.value.toFixed(2)} W): ${HINTS[r.top.name]}` : 'ok' })));
  }
}, 60);

$('#va-src').addEventListener('change', (e) => {
  st.src = e.target.value;
  $('#va-vin-row').hidden = st.src !== 'flagship';
  $('#va-saved-row').hidden = st.src !== 'saved';
  refreshSaved();
  run();
});
$('#va-mode').addEventListener('change', (e) => {
  $('#va-table-row').hidden = e.target.value !== 'table';
  $('#va-formula-row').hidden = e.target.value !== 'formula';
  run();
});
for (const id of ['va-table', 'va-formula', 'va-saved']) $('#' + id).addEventListener('input', run);
$('#va-saved').addEventListener('change', run);
slider('va-vin', (v) => v + ' V', (v) => { st.vin = v; run(); });
refreshSaved();
