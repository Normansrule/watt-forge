// home.js -- live flagship readout in the hero.
import * as F from '../model/flagship.js';
import { donut } from '../ui/charts.js';
import { $, slider, groupLosses, pct, debounce } from '../ui/ui.js';

const p = F.defaultParams();
let vin = 36, load = 0.75;
const run = debounce(() => {
  const pout = load * F.pRated(p, vin);
  const r = F.best(vin, 48, pout, p);
  $('#h-eta').textContent = pct(r.eta, 2);
  $('#h-mode').textContent = r.label.replace('buckboost', 'buck-boost');
  $('#h-fs').textContent = (r.fs / 1e3).toFixed(0) + ' kHz';
  $('#h-p').textContent = pout.toFixed(0) + ' W';
  donut($('#h-donut'), groupLosses(r.losses), { center: r.loss_total.toFixed(2) + ' W', sub: 'total loss' });
}, 20);
slider('h-vin', (v) => v.toFixed(1) + ' V', (v) => { vin = v; run(); });
slider('h-load', (v) => v + ' %', (v) => { load = v / 100; run(); });
