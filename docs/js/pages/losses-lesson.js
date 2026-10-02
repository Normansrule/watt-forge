// losses-lesson.js -- live loss budget of a synchronous buck.
import { design } from '../model/topologies.js';
import { switching } from '../model/devices.js';
import { donut, barList } from '../ui/charts.js';
import { $, h, slider, pct, groupLosses, LOSS_NAMES } from '../ui/ui.js';

const sel = $('#lb-dev');
for (const d of switching()) sel.append(h('option', { value: d.id, text: `${d.id} (${d.tech}, ${d.vds} V)` }));
sel.value = 'EPC2302';
const st = { f: 300e3, p: 120, rip: 0.3 };
function run() {
  const r = design({ topology: 'buck', vin: 48, vout: 12, pout: st.p, fs: st.f, ripple_frac: st.rip, device: sel.value });
  $('#lb-eta').textContent = pct(r.eta);
  donut($('#lb-donut'), groupLosses(r.losses), { center: r.total_loss.toFixed(2) + ' W', sub: 'total loss' });
  const items = Object.entries(r.losses).map(([k, v]) => ({ name: LOSS_NAMES[k] || k, value: v, cls: 'c1' })).sort((a, b) => b.value - a.value);
  barList($('#lb-bars'), items);
}
sel.addEventListener('change', run);
slider('lb-f', (v) => v + ' kHz', (v) => { st.f = v * 1e3; run(); });
slider('lb-p', (v) => v + ' W', (v) => { st.p = v; run(); });
slider('lb-rip', (v) => v.toFixed(1) + 'x', (v) => { st.rip = v; run(); });
