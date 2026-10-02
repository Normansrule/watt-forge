// devices-lesson.js -- device table with figures of merit.
import { DEVICES } from '../data/devices.js';
import * as D from '../model/devices.js';
import { $, h } from '../ui/ui.js';

const tb = $('#dev-table tbody');
for (const d of DEVICES) {
  const q50 = D.qoss(d, 50) * 1e9;
  const est = d.verified.includes('qoss_nc') && d.qoss_v === 50 ? '' : ' (est.)';
  tb.append(h('tr', {},
    h('td', { text: d.id }), h('td', { text: d.tech }), h('td', { class: 'r', text: d.vds + ' V' }),
    h('td', { class: 'r', text: d.rds_max_mohm + ' mOhm' }), h('td', { class: 'r', text: d.qg_nc + ' nC' }),
    h('td', { class: 'r', text: `${d.qoss_nc} nC @ ${d.qoss_v} V` }), h('td', { class: 'r', text: d.qrr_nc + ' nC' }),
    h('td', { class: 'r', text: (d.rds_max_mohm * d.qg_nc).toFixed(0) }),
    h('td', { class: 'r', text: (d.rds_max_mohm * q50).toFixed(0) + est }),
    h('td', {}, h('a', { href: d.url, rel: 'noopener noreferrer', text: 'datasheet' }))));
}
