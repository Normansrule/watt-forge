// sources.js -- full reference list grouped by category.
import { REFERENCES } from '../data/references.js';
import { card } from './frontier.js';
import { $, h } from '../ui/ui.js';

$('#src-verified').textContent = `Last verified: ${REFERENCES.last_verified}. Generated from data/references.json (also rendered as docs/REFERENCES.md).`;
const box = $('#src-list');
const cats = [...new Set(REFERENCES.references.map((r) => r.category))];
for (const c of cats) {
  box.append(h('h2', { text: c }));
  for (const r of REFERENCES.references.filter((x) => x.category === c)) box.append(card(r));
}
