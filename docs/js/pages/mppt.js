// mppt.js -- closed-loop MPPT sandbox: JS reference controller + PV panel model + flagship efficiency.
import * as PV from '../model/pv.js';
import * as F from '../model/flagship.js';
import { Ctrl, S, M, STATE_NAMES, MODE_NAMES } from '../model/control.js';
import { lineChart } from '../ui/charts.js';
import { $, slider } from '../ui/ui.js';

const panel = PV.defaultPanel();
const fp = F.defaultParams();
const DURATION = 12000; // ticks (ms)
const st = { scn: 'shade', g: 900, sh: 1, speed: 40, running: true };

function env(tick) {
  const t = tick / 1000;
  switch (st.scn) {
    case 'shade': { const s = t > 4 && t < 9 ? 0.25 : 1; return { g: [950, 950, 950 * s], t: 40, vout: 48 }; }
    case 'clouds': { const g = 900 - 380 * Math.max(0, Math.sin(t * 1.3)) ** 2 - 200 * Math.max(0, Math.sin(t * 3.1 + 1)) ** 4; return { g: [g, g, g], t: 42, vout: 48 }; }
    case 'morning': { const g = 150 + 850 * Math.min(1, t / 11); return { g: [g, g, g], t: 20 + 25 * Math.min(1, t / 11), vout: 48 }; }
    case 'cv': return { g: [1000, 1000, 1000], t: 40, vout: 52 + 6.2 * Math.min(1, t / 10) };
    case 'bypass': return { g: [1000, 1000, 1000], t: 25, vout: 40 };
    default: return { g: [st.g, st.g, st.g * st.sh], t: 40, vout: 48 };
  }
}

let ctrl, out, tick, hist, eAvail, eHarv, eBatt, eta, mppCache;
function reset() {
  ctrl = new Ctrl();
  out = { state: S.INIT, mode: M.OFF, vin_ref: 0, fs: 0, d1: 0, d2: 0 };
  tick = 0; hist = []; eAvail = 0; eHarv = 0; eBatt = 0; eta = 0.99; mppCache = new Map();
}
function mpp(e) {
  const key = e.g.map((x) => x.toFixed(0)).join(',') + '|' + e.t.toFixed(1);
  if (!mppCache.has(key)) { if (mppCache.size > 400) mppCache.clear(); mppCache.set(key, PV.globalMpp(e.g, e.t, panel, 120)); }
  return mppCache.get(key);
}
function step() {
  const e = env(tick);
  let vin, iin;
  const on = (out.state === S.TRACK || out.state === S.SWEEP || out.state === S.BYPASS) && out.mode !== M.OFF;
  if (on) { vin = out.vin_ref; iin = PV.panelCurrent(vin, e.g, e.t, panel); } else { vin = PV.panelVoltage(0, e.g, e.t, panel); iin = 0; }
  out = ctrl.tick({ vin, iin, vout: e.vout, iout: 0, temp: 40 });
  const p = vin * iin;
  const m = mpp(e);
  if (tick % 50 === 0 && p > 1) {
    if (out.mode === M.BYPASS) eta = F.bypass(e.vout, p, fp).eta;
    else if (out.mode !== M.OFF) eta = F.best(Math.min(Math.max(vin, 12), 60), Math.min(Math.max(e.vout, 40), 58), Math.min(p, 400), fp).eta;
  }
  if (tick >= 1000) { eAvail += m.p / 1000; eHarv += p / 1000; eBatt += (p * eta) / 1000; }
  if (tick % 20 === 0) hist.push({ t: tick / 1000, p, pm: m.p, v: vin, vm: m.v, state: out.state });
  tick++;
}
function render() {
  $('#mp-state').textContent = STATE_NAMES[out.state];
  $('#mp-mode').textContent = MODE_NAMES[out.mode];
  $('#mp-fs').textContent = out.fs ? (out.fs / 1e3).toFixed(0) + ' kHz' : '-';
  $('#mp-t').textContent = (tick / 1000).toFixed(1) + ' s';
  $('#mp-trk').textContent = eAvail > 0 ? ((100 * eHarv) / eAvail).toFixed(2) + ' %' : '-';
  $('#mp-e').textContent = (eBatt / 3600).toFixed(3) + ' Wh';
  lineChart($('#mp-pchart'), { height: 220, title: 'Panel power', series: [
    { name: 'available (global MPP)', cls: 'c3', pts: hist.map((x) => [x.t, x.pm]), endDot: false },
    { name: 'extracted', cls: 'c1', pts: hist.map((x) => [x.t, x.p]), endDot: true }],
  x: { label: 'time [s]', min: 0, max: DURATION / 1000 }, y: { label: 'W', min: 0, max: 420 }, tipFmt: (y) => y.toFixed(1) + ' W' });
  lineChart($('#mp-vchart'), { height: 200, title: 'Panel voltage', series: [
    { name: 'MPP voltage', cls: 'c3', pts: hist.map((x) => [x.t, x.vm]), endDot: false },
    { name: 'operating point', cls: 'c2', pts: hist.map((x) => [x.t, x.v]), endDot: true }],
  x: { label: 'time [s]', min: 0, max: DURATION / 1000 }, y: { label: 'V', min: 10, max: 55 }, tipFmt: (y) => y.toFixed(2) + ' V' });
}
let last = 0;
function loop(ts) {
  if (st.running && tick < DURATION) {
    for (let k = 0; k < st.speed && tick < DURATION; k++) step();
    if (ts - last > 90) { render(); last = ts; }
  } else if (tick >= DURATION) { render(); st.running = false; $('#mp-run').textContent = 'Run'; }
  requestAnimationFrame(loop);
}
$('#mp-run').addEventListener('click', () => {
  if (tick >= DURATION) reset();
  st.running = !st.running;
  $('#mp-run').textContent = st.running ? 'Pause' : 'Run';
});
$('#mp-reset').addEventListener('click', () => { reset(); st.running = true; $('#mp-run').textContent = 'Pause'; });
$('#mp-scn').addEventListener('change', (e) => { st.scn = e.target.value; reset(); st.running = true; $('#mp-run').textContent = 'Pause'; });
slider('mp-g', (v) => v + ' W/m^2', (v) => { st.g = v; });
slider('mp-sh', (v) => v + ' %', (v) => { st.sh = v / 100; });
slider('mp-speed', (v) => v + ' ticks/frame', (v) => { st.speed = v; });
if (matchMedia('(prefers-reduced-motion: reduce)').matches) st.speed = 200;
reset();
requestAnimationFrame(loop);
