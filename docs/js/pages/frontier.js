// frontier.js -- research cards rendered from the canonical reference list.
import { REFERENCES } from '../data/references.js';
import { $, h } from '../ui/ui.js';

export function card(r) {
  const link = r.doi ? `https://doi.org/${r.doi}` : r.url;
  const status = r.status.startsWith('VERIFIED') ? '' : ' warn';
  return h('div', { class: 'bench' },
    h('h3', {}, h('a', { href: link, rel: 'noopener noreferrer', text: r.title })),
    h('p', { class: 'note', text: `${r.authors}${r.year ? ', ' + r.year : ''}. ${r.venue}.${r.doi ? ' DOI ' + r.doi : ''}` }),
    r.headline ? h('p', {}, h('b', { text: 'Headline: ' }), r.headline) : null,
    r.conditions ? h('p', { class: 'note' }, h('b', { text: 'Exact conditions: ' }), r.conditions) : null,
    h('p', { text: r.summary }),
    h('span', { class: 'pill' + status, text: r.status }));
}

const box = $('#fr-cards');
if (box) {
  $('#fr-verified').textContent = `Last verified: ${REFERENCES.last_verified}.`;
  const cats = ['Piezoelectric', 'High-ratio hybrid SC', 'Flying-capacitor buck-boost', 'Bidirectional GaN', 'GaN buck-boost', 'Hybrid SC for PV', 'Medium voltage'];
  for (const c of cats) {
    const refs = REFERENCES.references.filter((r) => r.category === c);
    if (!refs.length) continue;
    if (c !== 'Piezoelectric') box.append(h('h2', { text: c }));
    for (const r of refs) box.append(card(r));
  }
}
