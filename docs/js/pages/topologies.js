// topologies.js -- topology picker, animated schematic, ideal vs lossy ratio.
import * as C from '../model/core.js';
import { lineChart } from '../ui/charts.js';
import { $, h, slider } from '../ui/ui.js';

const T = {
  buck: { name: 'Buck (step-down)', img: 'anim_buck.svg', eq: 'M = D', ideal: C.mBuck, lossy: C.mBuckLossy,
    lesson: 'Continuous output current, pulsed input current. The switch blocks Vin and carries the load current while on. Workhorse for any step-down: point-of-load regulators, battery chargers from a higher bus.' },
  boost: { name: 'Boost (step-up)', img: 'anim_boost.svg', eq: 'M = 1 / (1 - D)', ideal: C.mBoost, lossy: C.mBoostLossy,
    lesson: 'Continuous input current (kind to solar panels and batteries), pulsed output current. Switches block Vout. Inductor current is Iout/(1-D): at high gain it gets large.' },
  buck_boost: { name: 'Inverting buck-boost', img: 'anim_buck_boost.svg', eq: 'M = -D / (1 - D)', ideal: C.mBuckBoost, lossy: C.mBuckBoostLossy,
    lesson: 'Steps up or down with one inductor, but inverts polarity and both terminal currents are pulsed. Switches block Vin + |Vout|, the price of the single-inductor trick.' },
  sepic: { name: 'SEPIC', img: 'anim_sepic.svg', eq: 'M = D / (1 - D)', ideal: C.mSepic, lossy: null,
    lesson: 'Non-inverting up/down with continuous input current, at the cost of a second inductor and a coupling capacitor that carries the full load current as ripple. Popular in LED drivers and automotive rails.' },
  cuk: { name: 'Cuk', img: 'anim_cuk.svg', eq: 'M = -D / (1 - D)', ideal: C.mCuk, lossy: null,
    lesson: 'Energy moves through a capacitor instead of an inductor. Both input and output currents are continuous, so filtering is easy; the output is inverted and the coupling capacitor is heavily stressed.' },
  flyback: { name: 'Flyback (isolated)', img: 'anim_flyback.svg', eq: 'M = n D / (1 - D)', ideal: (d) => C.mFlyback(d, 1), lossy: null,
    lesson: 'A buck-boost whose inductor is split into two coupled windings: isolation and any ratio via n = Ns/Np. Leakage inductance energy must be clamped or recycled, which dominates its loss at higher power.' },
  four_switch: { name: 'Four-switch buck-boost', img: 'anim_four_switch.svg', eq: 'M = D1 / (1 - D2)', ideal: (d) => C.mFourSwitch(d, d), lossy: null,
    lesson: 'Non-inverting, one inductor, low switch stress (each leg blocks only its own bus). Runs as a plain buck or plain boost away from unity, both legs only near Vin = Vout. The skeleton of the flagship.' },
};
let cur = 'buck';
const st = { d: 0.5, r: 5, ron: 0.05 };

function pick() {
  const t = T[cur];
  $('#t-name').textContent = t.name;
  $('#t-eq').textContent = t.eq;
  $('#t-lesson').textContent = t.lesson;
  const img = $('#t-img');
  img.src = '../img/' + t.img;
  img.alt = `Animated ${t.name} schematic with current paths and waveforms`;
  for (const b of document.querySelectorAll('#t-pick button')) b.setAttribute('aria-checked', b.dataset.k === cur ? 'true' : 'false');
  draw();
}
function draw() {
  const t = T[cur];
  const ideal = [], lossy = [];
  for (let d = 0.02; d <= 0.951; d += 0.01) {
    ideal.push([d, Math.abs(t.ideal(d))]);
    if (t.lossy) lossy.push([d, Math.abs(t.lossy(d, st.r, st.ron, 0))]);
  }
  const mi = Math.abs(t.ideal(st.d));
  $('#t-mi').textContent = mi.toFixed(3);
  $('#t-ml').textContent = t.lossy ? Math.abs(t.lossy(st.d, st.r, st.ron, 0)).toFixed(3) : 'n/a';
  const series = [{ name: 'ideal', cls: 'c1', pts: ideal, endDot: false }];
  if (t.lossy) series.push({ name: 'with resistance', cls: 'c2', pts: lossy, endDot: false });
  lineChart($('#t-chart'), { height: 260, title: 'Conversion ratio |M| vs duty cycle', series, x: { label: 'D', min: 0, max: 1 },
    y: { label: '|M|', min: 0, max: Math.min(8, Math.max(...ideal.map((p) => p[1])) * 1.05) }, marks: [{ x: st.d, y: Math.min(mi, 8), cls: 'c1' }],
    tipFmt: (y) => y.toFixed(3) });
}
const pickRow = $('#t-pick');
for (const k of Object.keys(T)) {
  pickRow.append(h('button', { type: 'button', class: 'ghost', role: 'radio', 'data-k': k, text: T[k].name.split(' (')[0],
    onclick: () => { cur = k; pick(); } }));
}
slider('t-d', (v) => v.toFixed(2), (v) => { st.d = v; draw(); });
slider('t-r', (v) => v + ' ohm', (v) => { st.r = v; draw(); });
slider('t-ron', (v) => v + ' mOhm', (v) => { st.ron = v / 1000; draw(); });
pick();
