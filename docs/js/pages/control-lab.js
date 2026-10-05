// control-lab.js -- MPPT leaderboard, live races in a worker, tuning, efficiency controls, daily energy.
import { CONTROL_BENCHMARK as B } from '../data/control_benchmark.js';
import { CONTROL_EFFICIENCY as EF } from '../data/control_efficiency.js';
import { ETA_TABLE } from '../data/eta_table.js';
import * as X from '../model/mppt.js';
import * as EC from '../model/effctl.js';
import * as F from '../model/flagship.js';
import { lineChart, barList } from '../ui/charts.js';
import { $, h, slider, pct, debounce, wireRepoLinks } from '../ui/ui.js';

const KEYS = Object.keys(B.algorithms);
const PROFILE_KEYS = Object.keys(B.profiles);
const SHORT = { en50530_high: 'Ramps 30-100 %', en50530_low: 'Ramps 10-50 %', clouds: 'Clouds', shading: 'Shading', steady: 'Steady' };
const MAX_SEL = 6;
const fmtPct = (x, d = 2) => `${(100 * x).toFixed(d)} %`;

// ------------------------------------------------------------------ worker (falls back to the main thread)
let worker = null, reqId = 0;
const pending = new Map();
function getWorker() {
  if (worker !== null) return worker;
  try {
    worker = new Worker(new URL('../workers/control-worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = (ev) => { const p = pending.get(ev.data.id); if (p) p(ev.data); };
    worker.onerror = () => { worker = false; };
  } catch { worker = false; }
  return worker;
}
let mainEta = null, mainOracle = null;
function runJob(job, onProgress) {
  return new Promise((resolve, reject) => {
    const w = getWorker();
    if (w) {
      const id = ++reqId;
      pending.set(id, (d) => {
        if (d.error) { pending.delete(id); reject(new Error(d.error)); }
        else if (d.done) { pending.delete(id); resolve(d.results); }
        else onProgress?.(d.progress);
      });
      w.postMessage({ ...job, id });
      return;
    }
    // main-thread fallback, one tracker per frame so the page stays responsive
    mainEta = mainEta || new X.EtaTable(ETA_TABLE);
    mainOracle = mainOracle || new X.MppOracle();
    const prof = X.getProfile(job.profile);
    const out = {};
    const keys = [...job.keys];
    const total = keys.length;
    const step = () => {
      const key = keys.shift();
      if (!key) { resolve(out); return; }
      const r = X.run(X.makeTracker(key, (job.params || {})[key] || {}), prof, { seed: 7, eta: mainEta, oracle: mainOracle,
        noise: job.noise !== false, sigmaV: job.sigmaV, sigmaI: job.sigmaI, recordEvery: job.recordEvery });
      out[key] = { ...r, min: r.eta_mppt, max: r.eta_mppt };
      onProgress?.((total - keys.length) / total);
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

// ------------------------------------------------------------------ leaderboard
function leaderboard() {
  const head = $('#cl-board thead'), body = $('#cl-board tbody');
  head.append(h('tr', {}, h('th', { text: '#' }), h('th', { text: 'Tracker' }), h('th', { class: 'r', text: 'Overall' }),
    ...PROFILE_KEYS.map((p) => h('th', { class: 'r', text: SHORT[p], title: B.profiles[p] })), h('th', { class: 'r', text: 'System' })));
  const order = [...KEYS].sort((a, b) => B.overall[b].eta_mppt - B.overall[a].eta_mppt);
  const colBest = {};
  for (const p of PROFILE_KEYS) colBest[p] = Math.max(...KEYS.map((k) => B.results[p][k].eta_mppt));
  const bestOverall = Math.max(...KEYS.map((k) => B.overall[k].eta_mppt));
  const bestSys = Math.max(...KEYS.map((k) => B.overall[k].eta_sys));
  // heat: distance below the column best, in percentage points
  const heat = (x, best) => { const d = 100 * (best - x); return d < 0.05 ? 'h0' : d < 0.3 ? 'h1' : d < 1 ? 'h2' : d < 5 ? 'h3' : 'h4'; };
  order.forEach((k, n) => {
    const a = B.algorithms[k];
    const cell = (x, best, extra = '') => h('td', { class: `r ${heat(x, best)}${x === best ? ' best' : ''}${extra}`, text: fmtPct(x) });
    body.append(h('tr', {},
      h('td', { text: String(n + 1) }),
      h('td', {}, h('span', { class: 'algo', text: a.name }), ' ', h('span', { class: 'pill', text: a.family })),
      cell(B.overall[k].eta_mppt, bestOverall),
      ...PROFILE_KEYS.map((p) => {
        const r = B.results[p][k];
        const td = cell(r.eta_mppt, colBest[p]);
        td.title = `${SHORT[p]}: ${fmtPct(r.eta_mppt, 3)} (seeds ${fmtPct(r.eta_mppt_min, 3)} to ${fmtPct(r.eta_mppt_max, 3)}), ${r.e_lost_J.toFixed(0)} J lost`;
        return td;
      }),
      cell(B.overall[k].eta_sys, bestSys)));
  });
  $('#cl-board-note').textContent = `Overall = energy-weighted over all five profiles. Darker cells are further below the best in their column; hover a cell for the seed spread. Plant: ${B.dt * 1000} ms tick, noise ${B.plant.sigma_v * 1000} mV / ${B.plant.sigma_i * 1000} mA, seeds ${B.seeds.join(', ')}.`;
}

// ------------------------------------------------------------------ race
const sel = new Set(['po', 'vsinc', 'esc', 'pso', 'scan']);
function chips() {
  const fs = $('#cl-algos');
  for (const k of KEYS) {
    const id = `chip-${k}`;
    const cb = h('input', { type: 'checkbox', id, value: k, checked: sel.has(k) });
    cb.addEventListener('change', () => {
      if (cb.checked) sel.add(k); else sel.delete(k);
      for (const other of fs.querySelectorAll('input')) other.disabled = !other.checked && sel.size >= MAX_SEL;
    });
    fs.append(h('label', { class: 'chip', for: id }, cb, B.algorithms[k].name));
  }
  for (const other of fs.querySelectorAll('input')) other.disabled = !other.checked && sel.size >= MAX_SEL;
  fs.append(h('p', { class: 'note', text: `Up to ${MAX_SEL} at a time, so every line keeps a distinct colour.` }));
}

async function race() {
  const profile = $('#cl-profile').value;
  const keys = KEYS.filter((k) => sel.has(k));
  if (!keys.length) { $('#cl-status').textContent = 'Pick at least one tracker.'; return; }
  const noise = +$('#cl-noise').value;
  const nTicks = X.getProfile(profile).length;
  const btn = $('#cl-run');
  btn.disabled = true;
  const prog = $('#cl-prog');
  prog.parentElement.hidden = false;
  prog.style.width = '0%';
  $('#cl-status').textContent = 'Running...';
  const t0 = performance.now();
  try {
    const res = await runJob({ profile, keys, seeds: [7], noise: noise > 0, sigmaV: X.SIGMA_V * noise, sigmaI: X.SIGMA_I * noise,
      recordEvery: Math.max(1, Math.round(nTicks / 700)) }, (p) => { prog.style.width = `${(100 * p).toFixed(0)}%`; });
    drawRace(res, keys);
    $('#cl-status').textContent = `Done in ${((performance.now() - t0) / 1000).toFixed(1)} s, ${nTicks.toLocaleString()} ticks per tracker.`;
  } catch (e) {
    $('#cl-status').textContent = `Could not run: ${e.message}`;
  } finally {
    btn.disabled = false;
    prog.parentElement.hidden = true;
  }
}

function drawRace(res, keys) {
  const cls = (i) => `c${(i % 6) + 1}`;
  const first = res[keys[0]].trace;
  const t = first.t;
  const series = keys.map((k, i) => ({ name: B.algorithms[k].name, cls: cls(i), pts: res[k].trace.p.map((p, j) => [t[j], p]), endDot: false }));
  lineChart($('#cl-pchart'), { title: 'Panel power (dashed: available at the global maximum)', series, target: first.pmpp.map((p, j) => [t[j], p]),
    x: { label: 'time (s)', fmt: (v) => v.toFixed(0) }, y: { label: 'W', min: 0, fmt: (v) => v.toFixed(0) }, height: 300,
    tipFmt: (v) => `${v.toFixed(1)} W` });
  lineChart($('#cl-vchart'), { title: 'Panel voltage each tracker chose', series: keys.map((k, i) => ({ name: B.algorithms[k].name, cls: cls(i),
    pts: res[k].trace.v.map((v, j) => [t[j], v]), endDot: false })), x: { label: 'time (s)', fmt: (v) => v.toFixed(0) },
    y: { label: 'V', fmt: (v) => v.toFixed(0) }, height: 240, tipFmt: (v) => `${v.toFixed(2)} V` });
  const items = keys.map((k, i) => ({ name: `${B.algorithms[k].name}: ${fmtPct(res[k].eta_mppt)}`, value: res[k].e_lost_J, cls: cls(i) }))
    .sort((a, b) => a.value - b.value);
  const box = $('#cl-loss');
  box.textContent = '';
  box.append(h('h3', { text: 'Energy left on the panel (J) and dynamic MPPT efficiency' }));
  const list = h('div', { class: 'bars wide' });
  box.append(list);
  barList(list, items, 'J');
}

// ------------------------------------------------------------------ tune one
const TUNE_SPEC = {
  po: { step: [0.05, 2, 0.05, 'V'], period: [1, 8, 1, 'ticks'] },
  vspo: { gain: [0.005, 0.2, 0.005, 'V/(W/V)'], step_min: [0.02, 1, 0.02, 'V'] },
  inc: { step: [0.05, 2, 0.05, 'V'], tol: [0, 0.1, 0.001, ''] },
  vsinc: { gain: [0.005, 0.3, 0.005, 'V/(W/V)'], step_min: [0.02, 1, 0.02, 'V'] },
  focv: { k: [0.7, 0.92, 0.01, ''], every: [50, 3000, 50, 'updates'] },
  esc: { amp: [0.1, 2, 0.05, 'V'], gain: [0.001, 0.05, 0.001, ''] },
  pso: { w: [0.1, 0.9, 0.05, ''], restart: [0.05, 0.6, 0.01, ''] },
  scan: { points: [6, 60, 1, ''], drop: [0.2, 0.95, 0.01, ''] },
};
function tuneControls() {
  const k = $('#tn-algo').value;
  const box = $('#tn-params');
  box.textContent = '';
  for (const [name, [lo, hi, st, unit]] of Object.entries(TUNE_SPEC[k])) {
    const id = `tn-${name}`;
    const val = B.params[k][name];
    box.append(h('div', { class: 'control' }, h('label', { for: id }, `${name}${unit ? ` (${unit})` : ''} `, h('output', { for: id })),
      h('input', { id, type: 'range', min: lo, max: hi, step: st, value: val, 'data-name': name })));
    slider(id, (v) => (+v).toString());
  }
}
async function tuneRun() {
  const k = $('#tn-algo').value;
  const profile = $('#tn-profile').value;
  const mine = {};
  for (const inp of $('#tn-params').querySelectorAll('input')) mine[inp.dataset.name] = +inp.value;
  $('#tn-status').textContent = 'Running both...';
  const n = X.getProfile(profile).length;
  try {
    const [a, b] = await Promise.all([
      runJob({ profile, keys: [k], params: { [k]: mine }, seeds: [7], recordEvery: Math.max(1, Math.round(n / 600)) }),
      runJob({ profile, keys: [k], seeds: [7], recordEvery: Math.max(1, Math.round(n / 600)) })]);
    const em = a[k].eta_mppt, et = b[k].eta_mppt;
    $('#tn-mine').textContent = fmtPct(em, 3);
    $('#tn-tuned').textContent = fmtPct(et, 3);
    $('#tn-diff').textContent = `${(100 * (em - et)).toFixed(3)} pts`;
    const t = b[k].trace.t;
    lineChart($('#tn-chart'), { title: 'Panel power', series: [
      { name: 'your settings', cls: 'c2', pts: a[k].trace.p.map((p, j) => [t[j], p]), endDot: false },
      { name: 'tuned', cls: 'c1', pts: b[k].trace.p.map((p, j) => [t[j], p]), endDot: false }],
    target: b[k].trace.pmpp.map((p, j) => [t[j], p]), x: { label: 'time (s)', fmt: (v) => v.toFixed(0) }, y: { label: 'W', min: 0 }, height: 280,
    tipFmt: (v) => `${v.toFixed(1)} W` });
    $('#tn-status').textContent = '';
  } catch (e) { $('#tn-status').textContent = `Could not run: ${e.message}`; }
}

// ------------------------------------------------------------------ efficiency controls
const P = F.defaultParams();
function effUpdate() {
  const vin = +$('#ef-vin').value;
  const pmax = F.pRated(P, vin);
  const pin = $('#ef-p');
  if (+pin.value > pmax) pin.value = String(Math.floor(pmax / 5) * 5);
  $('output[for="ef-p"]').textContent = `${(+pin.value).toFixed(0)} W`;
  const pout = +pin.value;
  const kappa = EC.kappaEstimate(vin, pout);
  const op = EC.operatingPoint(vin, 48, pout, kappa, P);
  const L = op.loss;
  $('#ef-saved').textContent = `${(L.base - L.bypass).toFixed(2)} W`;
  $('#ef-eta0').textContent = fmtPct(pout / (pout + L.base));
  $('#ef-eta1').textContent = fmtPct(pout / (pout + L.bypass));
  const steps = [['Fixed 100 kHz, 10 ns', L.base, 'c4'], ['+ adaptive frequency', L.fs, 'c3'], ['+ adaptive dead time', L.td, 'c3'],
    ['+ burst mode', L.burst, 'c3'], ['+ bypass', L.bypass, 'c3']];
  const box = $('#ef-steps');
  box.textContent = '';
  box.append(h('h3', { text: 'Total converter loss, controls added in turn' }));
  const list = h('div', { class: 'bars wide' }); box.append(list);
  barList(list, steps.map(([name, v, cls]) => ({ name, value: v, cls })), 'W', L.base);
  const b = op.burst;
  $('#ef-burst').textContent = b.active && b.loss_total < L.td
    ? `Burst mode on: switching at ${b.p_burst} W for ${(100 * b.delta).toFixed(0)} % of the time, ${b.f_burst} bursts/s. Panel ripple ${b.dv_pp.toFixed(2)} V peak-to-peak costs ${b.parts.mismatch.toFixed(3)} W of MPPT mismatch; wake-ups cost ${b.parts.wake.toFixed(3)} W.`
    : (pout >= 0.9 * 160 ? 'Burst mode off: the load is too high to burst.' : 'Burst mode off: at this load the input ripple and idle housekeeping would cost more than burst saves.');
  // frequency curve: marks sit on the model curve at the setting the climb most often lands on
  const fc = op.fs.curve.filter((c) => c.loss !== null);
  const fsAt = (f) => op.fs.curve.find((c) => c.fs === f).loss;
  lineChart($('#ef-fs'), { title: 'Loss vs switching frequency', series: [{ name: 'model', cls: 'c1', pts: fc.map((c) => [c.fs / 1e3, c.loss]), endDot: false }],
    marks: [{ x: op.fs.fixed / 1e3, y: L.base, cls: 'c4', label: 'fixed' }, { x: op.fs.online / 1e3, y: fsAt(op.fs.online), cls: 'c1', label: 'hill climb' }],
    x: { label: 'kHz', fmt: (v) => v.toFixed(0) }, y: { label: 'W', fmt: (v) => v.toFixed(2) }, height: 240, tipFmt: (v) => `${v.toFixed(3)} W` });
  const tc = op.td.curve.filter((c) => c.loss !== null);
  const tdAt = (t) => op.td.curve.find((c) => Math.abs(c.td - t) < 1e-15).loss;
  lineChart($('#ef-td'), { title: 'Loss vs dead time (at the chosen frequency)', series: [{ name: 'model', cls: 'c3', pts: tc.map((c) => [c.td * 1e9, c.loss]), endDot: false }],
    marks: [{ x: P.t_dead * 1e9, y: op.td.loss_fixed, cls: 'c4', label: `fixed ${(P.t_dead * 1e9).toFixed(0)} ns` }, { x: op.td.online * 1e9, y: tdAt(op.td.online), cls: 'c3', label: 'hill climb' }],
    x: { label: 'ns', fmt: (v) => v.toFixed(0) }, y: { label: 'W', fmt: (v) => v.toFixed(2) }, height: 240, tipFmt: (v) => `${v.toFixed(3)} W` });
  $('#ef-hc').textContent = `Measurement resolution after averaging 5 s of readings: ${(op.sigma * 1000).toFixed(1)} mW; a step is kept only if it saves more than twice that. `
    + `Over ${EC.MC_SEEDS} noise trials the frequency climb reached the optimum ${(100 * op.fs.hit_rate).toFixed(0)} % of the time and the dead-time climb ${(100 * op.td.hit_rate).toFixed(0)} %; `
    + `the losses above are the mean over those trials. Near the optimum the gains fall below what the sensors can resolve, so the climb stops short.`;
}

// ------------------------------------------------------------------ a day of sun
function day() {
  const d = EF.day, e = d.energy_Wh;
  const water = $('#day-water');
  water.append(h('h3', { text: `Energy over the day (Wh), MPPT: global scan at ${fmtPct(d.eta_mppt)}` }));
  const rows = [
    ['Available at the maximum power point', e.available, 'c1'],
    ['Drawn from the panel (after MPPT)', e.after_mppt, 'c1'],
    ['Delivered, fixed 100 kHz and 10 ns', e.base, 'c1'],
    ['+ adaptive frequency', e.fs, 'c3'],
    ['+ adaptive dead time', e.td, 'c3'],
    ['+ burst mode', e.burst, 'c3'],
    ['+ bypass', e.bypass, 'c3'],
  ];
  const list = h('div', { class: 'bars wide' }); water.append(list);
  const lo = e.base * 0.97;
  barList(list, rows.map(([name, v, cls]) => ({ name, value: v - lo, cls })), 'Wh', e.available - lo);
  // relabel the values as absolute Wh (bars are drawn from a common baseline to make the differences visible)
  list.querySelectorAll('.val').forEach((el, i) => { el.textContent = `${rows[i][1].toFixed(1)} Wh`; });
  const gain = e.bypass - e.base;
  $('#day-note').textContent = `Bars start at ${lo.toFixed(0)} Wh so the differences show. Converter controls recover ${gain.toFixed(1)} Wh (${(100 * gain / e.base).toFixed(2)} % more energy delivered). `
    + `Bypass adds nothing on this day: the 72-cell panel's maximum power point (${Math.min(...d.rows.map((r) => r.vmp)).toFixed(0)}-${Math.max(...d.rows.map((r) => r.vmp)).toFixed(0)} V) never comes within 2 % of the ${d.vout} V battery.`;
  const t = d.rows.map((r) => r.h);
  lineChart($('#day-chart'), { title: 'Converter loss through the day', series: [
    { name: 'fixed settings', cls: 'c4', pts: d.rows.map((r) => [r.h, r.base]), endDot: false },
    { name: 'all controls', cls: 'c3', pts: d.rows.map((r) => [r.h, r.bypass]), endDot: false }],
  x: { label: 'hour', min: t[0], max: t[t.length - 1], fmt: (v) => `${v.toFixed(0)}:00` }, y: { label: 'W', min: 0, fmt: (v) => v.toFixed(1) }, height: 280,
  tipFmt: (v) => `${v.toFixed(2)} W` });
}

// ------------------------------------------------------------------ wire up
leaderboard();
for (const p of PROFILE_KEYS) { $('#cl-profile').append(h('option', { value: p, text: B.profiles[p] })); $('#tn-profile').append(h('option', { value: p, text: B.profiles[p] })); }
$('#cl-profile').value = 'shading';
$('#tn-profile').value = 'clouds';
chips();
slider('cl-noise', (v) => `${(+v).toFixed(1)}x`);
$('#cl-run').addEventListener('click', race);
for (const k of KEYS) $('#tn-algo').append(h('option', { value: k, text: B.algorithms[k].name }));
$('#tn-algo').value = 'po';
$('#tn-algo').addEventListener('change', tuneControls);
tuneControls();
$('#tn-run').addEventListener('click', tuneRun);
$('#tn-reset').addEventListener('click', tuneControls);
slider('ef-vin', (v) => `${v} V`, debounce(effUpdate, 30));
$('#ef-p').addEventListener('input', debounce(effUpdate, 30));
effUpdate();
day();
wireRepoLinks();
