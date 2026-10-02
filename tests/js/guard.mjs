// guard.mjs -- the browser netlist guard must give the same verdicts as Python and Rust.
// Run: node tests/js/guard.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { checkNetlist, NetlistRejected, parseSpiceNumber, parseMeasurements } from '../../docs/js/model/netlist-guard.js';
import { SPICE_PRESETS } from '../../docs/js/data/spice_presets.js';

const here = dirname(fileURLToPath(import.meta.url));
const text = readFileSync(join(here, '..', 'fixtures', 'guard_cases.txt'), 'utf8');
const cases = [];
let cur = null;
for (const line of text.split(/(?<=\n)/)) {
  if (line.startsWith('===')) { const [, verdict, name] = line.trim().split(/\s+/); cur = { name, ok: verdict === 'ok', net: '' }; cases.push(cur); }
  else if (cur) cur.net += line;
}
let fails = 0;
const verdict = (net) => { try { checkNetlist(net); return true; } catch (e) { if (e instanceof NetlistRejected) return false; throw e; } };
for (const c of cases) if (verdict(c.net) !== c.ok) { fails++; console.log(`FAIL ${c.name}: expected ${c.ok ? 'ok' : 'reject'}`); }
const big = '*x\n' + 'R1 a b 1\n'.repeat(30000);
if (verdict(big)) { fails++; console.log('FAIL: 30000-line netlist accepted'); }
for (const p of SPICE_PRESETS.presets) if (!verdict(p.netlist)) { fails++; console.log(`FAIL preset ${p.id} rejected`); }
const near = (a, b) => Math.abs(a - b) <= 1e-12 * Math.abs(b);
if (!near(parseSpiceNumber('10u'), 10e-6) || !near(parseSpiceNumber('1meg'), 1e6) || !near(parseSpiceNumber('2.5e-3'), 2.5e-3)) { fails++; console.log('FAIL numbers'); }
const m = parseMeasurements('pin                 =  4.009188e+02 from=  4.0e-04 to=  5.3e-04\nNo. of Data Rows : 3\n');
if (!near(m.pin, 400.9188)) { fails++; console.log('FAIL parseMeasurements', m); }
console.log(fails ? `${fails} guard checks failed` : `${cases.length + 2 + SPICE_PRESETS.presets.length} guard checks passed`);
process.exit(fails ? 1 : 0);
