// spice.js -- SPICE runner: guard + stored results on the web, live sandboxed ngspice in the desktop app.
import { SPICE_PRESETS } from '../data/spice_presets.js';
import { checkNetlist, parseMeasurements } from '../model/netlist-guard.js';
import { $, h, wireRepoLinks } from '../ui/ui.js';

const invoke = globalThis.__TAURI__?.core?.invoke ?? null;   // present only inside the desktop app
const presets = SPICE_PRESETS.presets;
const byId = Object.fromEntries(presets.map((p) => [p.id, p]));
const LABELS = { eta: 'Efficiency', pin: 'Input power (W)', pout: 'Output power (W)', ilavg: 'Average inductor current (A)', vout: 'Output voltage (V)', vavg: 'Average output (V)' };
const EXPECT_KEY = { eta: 'conduction_only_eta', pout: 'pout_W', vout: 'vout', vavg: 'vavg' };

function fmt(k, v) {
  if (v === undefined || v === null || !Number.isFinite(v)) return '-';
  return k === 'eta' ? `${(100 * v).toFixed(3)} %` : (Math.abs(v) >= 100 ? v.toFixed(2) : v.toPrecision(5));
}

function show(result, expect, src, ms) {
  const tb = $('#sp-tab tbody');
  tb.textContent = '';
  for (const [k, v] of Object.entries(result)) {
    const ek = EXPECT_KEY[k];
    const e = ek && expect ? expect[ek] : undefined;
    const diff = e === undefined ? '-' : k === 'eta' ? `${(100 * (v - e)).toFixed(4)} pts` : `${(100 * (v - e) / e).toFixed(3)} %`;
    tb.append(h('tr', {}, h('td', { text: LABELS[k] || k }), h('td', { class: 'r', text: fmt(k, v) }), h('td', { class: 'r', text: fmt(k, e) }), h('td', { class: 'r', text: diff })));
  }
  if (expect && expect.full_model_eta !== undefined) {
    tb.append(h('tr', {}, h('td', { text: 'Full model efficiency (all losses)' }), h('td', { class: 'r', text: '-' }), h('td', { class: 'r', text: fmt('eta', expect.full_model_eta) }), h('td', { class: 'r', text: '-' })));
  }
  $('#sp-src').textContent = src;
  $('#sp-time').textContent = ms === null ? 'build time' : `${(ms / 1000).toFixed(2)} s`;
}

function guard() {
  $('#sp-err').textContent = '';
  try {
    const w = checkNetlist($('#sp-net').value);
    $('#sp-guard').textContent = w.length ? 'Passed (with warning)' : 'Passed';
    if (w.length) $('#sp-err').textContent = w.join('; ');
    return true;
  } catch (e) {
    $('#sp-guard').textContent = 'Rejected';
    $('#sp-err').textContent = e.message;
    return false;
  }
}

function loadPreset() {
  const p = byId[$('#sp-preset').value];
  $('#sp-net').value = p.netlist;
  $('#sp-about').textContent = p.about;
  guard();
  show(p.result, p.expect, `stored (${SPICE_PRESETS.simulator})`, null);
  $('#sp-raw').textContent = invoke ? 'Press Run to simulate live.' : 'Run a netlist in the desktop app to see its raw output here.';
}

async function run() {
  if (!guard()) return;
  const text = $('#sp-net').value;
  const p = byId[$('#sp-preset').value];
  const unchanged = text === p.netlist;
  if (!invoke) {
    if (unchanged) { show(p.result, p.expect, `stored (${SPICE_PRESETS.simulator})`, null); return; }
    $('#sp-err').textContent = 'The web version does not execute netlists. Your edit passed the guard; run it in the desktop app (live ngspice) or restore the preset to see its stored result.';
    return;
  }
  const btn = $('#sp-run');
  btn.disabled = true; btn.textContent = 'Running...';
  const t0 = performance.now();
  try {
    const out = await invoke('simulate_netlist', { netlist: text });
    const meas = parseMeasurements(out);
    if (meas.pin && meas.pout) meas.eta = meas.pout / meas.pin;
    $('#sp-raw').textContent = out.slice(-20000);
    if (!Object.keys(meas).length) $('#sp-err').textContent = 'ngspice ran but reported no .meas results. Check the raw output.';
    show(meas, unchanged ? p.expect : null, 'ngspice, live', performance.now() - t0);
  } catch (e) {
    $('#sp-err').textContent = String(e);
  } finally {
    btn.disabled = false; btn.textContent = 'Run';
  }
}

for (const p of presets) $('#sp-preset').append(h('option', { value: p.id, text: p.label }));
$('#sp-preset').value = presets.find((p) => p.id.startsWith('flagship'))?.id ?? presets[0].id;
$('#sp-preset').addEventListener('change', loadPreset);
$('#sp-run').addEventListener('click', run);
$('#sp-check').addEventListener('click', guard);
$('#sp-reset').addEventListener('click', loadPreset);
$('#sp-env').textContent = invoke ? 'Desktop app: ngspice runs live in a sandbox' : `Web version: showing results stored at build time (${SPICE_PRESETS.simulator}). Get the desktop app to run edited netlists.`;
if (!invoke) $('#sp-env').classList.add('warn');
$('#sp-run').textContent = invoke ? 'Run' : 'Show result';
wireRepoLinks();
loadPreset();
