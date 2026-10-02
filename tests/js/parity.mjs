// parity.mjs -- the browser model must reproduce the Python model.
// Run: node tests/js/parity.mjs   (pytest runs it via tests/test_web.py)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as C from '../../docs/js/model/core.js';
import { design } from '../../docs/js/model/topologies.js';
import * as F from '../../docs/js/model/flagship.js';
import * as PV from '../../docs/js/model/pv.js';
import { Ctrl, line } from '../../docs/js/model/control.js';
import { compile } from '../../docs/js/model/expr.js';

const here = dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(readFileSync(join(here, '..', 'fixtures', 'parity.json'), 'utf8'));
let fails = 0, checks = 0;
function close(a, b, rel, what) {
  checks++;
  const ok = (a === b) || Math.abs(a - b) <= rel * Math.max(Math.abs(a), Math.abs(b), 1e-30);
  if (!ok) { fails++; console.log(`FAIL ${what}: js=${a} py=${b}`); }
}

// core
for (const [name, args, want] of fx.core) {
  let got;
  if (name === 'simulateSeriesParallel.r_out') got = C.simulateSeriesParallel(...args).r_out;
  else got = C[name](...args);
  close(got, want, 1e-12, `core.${name}(${JSON.stringify(args)})`);
}
// generic designer
for (const [spec, want] of fx.topologies) {
  const r = design(spec);
  close(r.eta, want.eta, 1e-10, `design ${spec.topology} eta`);
  close(r.total_loss, want.total_loss, 1e-9, `design ${spec.topology} loss`);
  close(r.l, want.l, 1e-12, `design ${spec.topology} L`);
  for (const k of Object.keys(want.losses)) close(r.losses[k] ?? 0, want.losses[k], 1e-9, `design ${spec.topology} ${k}`);
}
// flagship
const p = F.defaultParams();
for (const c of fx.flagship) {
  if (c.kind === 'evaluate') {
    const r = F.evaluate(...c.args, p);
    for (const k of ['eta', 'd1', 'd2', 'il', 'ripple_pp', 'cfly_ripple', 'phase']) close(r[k], c.out[k], 1e-9, `flagship ${c.args} ${k}`);
    checks++; if (r.n_hard !== c.out.n_hard) { fails++; console.log('FAIL n_hard', c.args, r.n_hard, c.out.n_hard); }
    for (const k of Object.keys(c.out.losses)) close(r.losses[k], c.out.losses[k], 1e-8, `flagship ${c.args} ${k}`);
  } else {
    const r = F.best(...c.args, p);
    close(r.eta, c.out.eta, 1e-9, `best ${c.args} eta`);
    close(r.fs, c.out.fs, 0, `best ${c.args} fs`);
    checks++; if (r.mode !== c.out.mode) { fails++; console.log('FAIL best mode', c.args); }
  }
}
// pv
const panel = PV.defaultPanel();
for (const c of fx.pv) {
  const m = PV.globalMpp(c.irr, c.t, panel);
  close(m.p, c.mpp.p, 1e-9, `mpp ${c.irr}`);
  for (const [v, i] of c.i_at) close(PV.panelCurrent(v, c.irr, c.t, panel), i, 1e-9, `pv I(${v})`);
}
// controller trace
const ctrl = new Ctrl();
let lines = 0;
for (const [[vin, iin, vout, iout, temp], want] of fx.control) {
  const got = line(ctrl.tick({ vin, iin, vout, iout, temp }));
  checks++; lines++;
  if (got !== want) { fails++; if (fails < 5) console.log(`FAIL ctrl line ${lines}: js='${got}' py='${want}'`); }
}
// safe expression evaluator
const f = compile('0.99 - 0.02*(1-p)^2 + min(v, 60)*0', ['p', 'v']);
close(f({ p: 0.5, v: 10 }), 0.99 - 0.02 * 0.25, 1e-15, 'expr');
for (const bad of ['alert(1)', 'p;1', 'constructor', '__proto__', 'toString(p)', 'constructor(p)', '(p', 'p)', 'window.x', 'p**2', '1e999999'.repeat(30)]) {
  checks++;
  let threw = false;
  try { compile(bad, ['p']); } catch { threw = true; }
  if (!threw) { fails++; console.log('FAIL expr accepted', bad.slice(0, 40)); }
}
console.log(`${checks - fails}/${checks} parity checks passed`);
process.exit(fails ? 1 : 0);
