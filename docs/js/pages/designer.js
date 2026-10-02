// designer.js -- topology designer with save / export / validated import.
import { design, TOPOLOGIES } from '../model/topologies.js';
import { switching } from '../model/devices.js';
import { donut, barList, lineChart } from '../ui/charts.js';
import { $, h, slider, pct, eng, store, groupLosses, LOSS_NAMES, debounce } from '../ui/ui.js';
import { validateDesign } from './designer-schema.js';

const form = $('#dz-form');
for (const [k, n] of TOPOLOGIES) $('#dz-top').append(h('option', { value: k, text: n }));
for (const d of switching()) $('#dz-dev').append(h('option', { value: d.id, text: `${d.id} (${d.tech}, ${d.vds} V)` }));
$('#dz-dev').value = 'EPC2302';

function readForm() {
  const f = new FormData(form);
  return {
    topology: f.get('topology'), vin: +f.get('vin'), vout: +f.get('vout'), pout: +f.get('pout'), fs_khz: +f.get('fs_khz'),
    ripple_frac: +f.get('ripple_frac'), device: f.get('device'), sync: $('#dz-sync').checked, dcr_mohm: +f.get('dcr_mohm'), n: +f.get('n'),
  };
}
function writeForm(d) {
  $('#dz-top').value = d.topology; $('#dz-vin').value = d.vin; $('#dz-vout').value = d.vout; $('#dz-p').value = d.pout;
  $('#dz-f').value = d.fs_khz; $('#dz-rip').value = d.ripple_frac; $('#dz-dev').value = d.device; $('#dz-sync').checked = d.sync;
  $('#dz-dcr').value = d.dcr_mohm; $('#dz-n').value = d.n;
  $('#dz-rip').dispatchEvent(new Event('input'));
}
const toSpec = (d, pout = d.pout) => ({ topology: d.topology, vin: d.vin, vout: d.vout, pout, fs: d.fs_khz * 1e3, ripple_frac: d.ripple_frac,
  device: d.device, sync: d.sync, dcr_mohm: d.dcr_mohm, n: d.n });

const run = debounce(() => {
  const err = $('#dz-err');
  err.textContent = '';
  let d;
  try { d = validateDesign(readForm()); } catch (e) { err.textContent = e.message; return; }
  if (d.topology === 'buck' && d.vout >= d.vin) { err.textContent = 'A buck can only step down: make Vout smaller than Vin, or pick another topology.'; return; }
  if (d.topology === 'boost' && d.vout <= d.vin) { err.textContent = 'A boost can only step up: make Vout larger than Vin, or pick another topology.'; return; }
  const r = design(toSpec(d));
  $('#dz-eta').textContent = pct(r.eta);
  $('#dz-d').textContent = r.d.toFixed(3);
  $('#dz-l').textContent = eng(r.l, 'H') + (r.l2 ? ` + ${eng(r.l2, 'H')}` : '');
  $('#dz-c').textContent = eng(r.c_out, 'F');
  $('#dz-il').textContent = `${r.il.toFixed(2)} A / ${r.delta_i.toFixed(2)} A`;
  $('#dz-vsw').textContent = r.v_switch.toFixed(1) + ' V';
  const notes = $('#dz-notes');
  notes.textContent = '';
  for (const n of r.notes) notes.append(h('li', { text: n }));
  if (r.d > 0.9 || r.d < 0.05) notes.append(h('li', { text: 'Extreme duty cycle: minimum on/off times and losses get hard to manage; consider another topology or a transformer.' }));
  donut($('#dz-donut'), groupLosses(r.losses), { center: r.total_loss.toFixed(2) + ' W', sub: 'total loss' });
  barList($('#dz-bars'), Object.entries(r.losses).map(([k, v]) => ({ name: LOSS_NAMES[k] || k, value: v, cls: 'c1' })).sort((a, b) => b.value - a.value));
  const pts = [];
  for (let f = 0.05; f <= 1.001; f += 0.05) pts.push([f * 100, 100 * design(toSpec(d, f * d.pout)).eta]);
  lineChart($('#dz-curve'), { height: 230, title: 'Efficiency vs load', series: [{ name: 'efficiency', cls: 'c1', pts }],
    x: { label: 'load [% of the power above]', min: 0, max: 100 }, y: { label: '%' }, tipFmt: (y) => y.toFixed(2) + ' %' });
}, 40);

form.addEventListener('input', run);
form.addEventListener('change', run);
slider('dz-rip', (v) => v.toFixed(2));

// ---- persistence
function refreshSaved() {
  const sel = $('#dz-saved');
  const all = store.get('designs', {});
  sel.textContent = '';
  sel.append(h('option', { value: '', text: Object.keys(all).length ? '(choose)' : '(none)' }));
  for (const k of Object.keys(all)) sel.append(h('option', { value: k, text: k }));
}
$('#dz-save').addEventListener('click', () => {
  const d = readForm();
  const name = `${d.topology} ${d.vin}V-${d.vout}V ${d.pout}W`;
  const all = store.get('designs', {});
  all[name] = d;
  $('#dz-err').textContent = store.set('designs', all) ? '' : 'This browser blocks storage, so the design could not be saved. Export it as JSON instead.';
  refreshSaved();
});
$('#dz-saved').addEventListener('change', (e) => {
  const all = store.get('designs', {});
  if (!e.target.value || !all[e.target.value]) return;
  try { writeForm(validateDesign(all[e.target.value])); run(); } catch (err) { $('#dz-err').textContent = 'Saved design is invalid: ' + err.message; }
});
$('#dz-export').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(readForm(), null, 1)], { type: 'application/json' });
  const a = h('a', { href: URL.createObjectURL(blob), download: 'watt-forge-design.json' });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
$('#dz-import').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  if (file.size > 10_000) { $('#dz-err').textContent = 'File too large: a design file is under 10 kB.'; return; }
  try { writeForm(validateDesign(JSON.parse(await file.text()))); run(); }
  catch (err) { $('#dz-err').textContent = 'Import rejected: ' + err.message; }
});
refreshSaved();
run();
