// devices-tool.js -- same converter, different transistor.
import * as F from '../model/flagship.js';
import { switching } from '../model/devices.js';
import { $, h, slider, pct, groupLosses, LOSS_GROUPS, debounce } from '../ui/ui.js';

const DEF = ['EPC2361', 'EPC2302', 'ISC030N10NM6', 'CSD19536KTT', 'IMT65R010M2H', 'C3M0015065K'];
const st = { vin: 36, load: 0.75, f: 150e3, rth: 20, ta: 40 };
const list = $('#dc-list');
for (const d of switching()) {
  const id = 'dc-' + d.id;
  list.append(h('label', { class: 'note', for: id }, h('input', { type: 'checkbox', id, value: d.id, checked: DEF.includes(d.id) }), ` ${d.id} (${d.tech}, ${d.vds} V) `), h('br'));
}
$('#dc-legend').append(...LOSS_GROUPS.map(([n], i) => h('span', {}, h('span', { class: `sw c${i + 1}` }), n)));

const run = debounce(() => {
  const ids = [...list.querySelectorAll('input:checked')].map((x) => x.value);
  const rows = ids.map((id) => {
    const p = { ...F.defaultParams(), switch: id };
    const mode = st.vin > 48.05 ? 'buck' : st.vin < 47.95 ? 'boost' : 'buckboost';
    const r = F.evaluate(st.vin, 48, st.load * F.pRated(p, st.vin), st.f, mode, p);
    const L = r.losses;
    const nSw = mode === 'buckboost' ? 8 : 4;
    const hot = L.switch_conduction / 4 + (L.coss + L.overlap + L.loop_ringing) / 2 + (L.dead_time + L.coss_hysteresis + L.gate) / nSw;
    return { id, r, hot, tj: st.ta + hot * st.rth };
  });
  const max = Math.max(...rows.map((x) => x.r.loss_total), 1e-9);
  const bars = $('#dc-bars');
  bars.textContent = '';
  for (const x of rows) {
    const track = h('div', { class: 'row' });
    for (const g of groupLosses(x.r.losses)) {
      const seg = h('div', { class: `bar ${g.cls}`, title: `${g.name}: ${g.value.toFixed(3)} W` });
      seg.style.width = (100 * g.value) / max * 0.82 + '%';
      seg.style.height = '16px';
      seg.style.marginRight = '2px';
      track.append(seg);
    }
    track.style.gap = '0';
    track.style.flexWrap = 'nowrap';
    bars.append(h('div', { class: 'barrow' }, h('span', { text: x.id }), track, h('span', { class: 'val', text: x.r.loss_total.toFixed(2) + ' W' })));
  }
  const tb = $('#dc-tab tbody');
  tb.textContent = '';
  for (const x of rows) {
    tb.append(h('tr', {}, h('td', { text: x.id }), h('td', { class: 'r', text: pct(x.r.eta) }), h('td', { class: 'r', text: x.r.loss_total.toFixed(2) + ' W' }),
      h('td', { class: 'r', text: x.hot.toFixed(2) + ' W' }), h('td', { class: 'r', text: x.tj.toFixed(0) + ' C' + (x.tj > 125 ? ' (too hot)' : '') })));
  }
}, 30);
list.addEventListener('change', run);
slider('dc-vin', (v) => v + ' V', (v) => { st.vin = v; run(); });
slider('dc-load', (v) => v + ' %', (v) => { st.load = v / 100; run(); });
slider('dc-f', (v) => v + ' kHz', (v) => { st.f = v * 1e3; run(); });
slider('dc-rth', (v) => v + ' K/W', (v) => { st.rth = v; run(); });
slider('dc-ta', (v) => v + ' C', (v) => { st.ta = v; run(); });
