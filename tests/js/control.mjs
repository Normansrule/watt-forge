// control.mjs -- the browser control library must reproduce the Python one.
// Fixture: tests/fixtures/control_parity.json (scripts/make_control_data.py). Run: node tests/js/control.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as X from '../../docs/js/model/mppt.js';
import * as EC from '../../docs/js/model/effctl.js';
import { ETA_TABLE } from '../../docs/js/data/eta_table.js';
import { CONTROL_BENCHMARK } from '../../docs/js/data/control_benchmark.js';

const here = dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(readFileSync(join(here, '..', 'fixtures', 'control_parity.json'), 'utf8'));
let fails = 0, checks = 0;
const close = (a, b, tol, what) => { checks++; if (!(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)))) { fails++; console.log(`FAIL ${what}: js=${a} py=${b}`); } };

// rng reference values (same as tests/test_control_lib.py)
const r = new X.XorShift32(1);
const ref = [270369, 67634689, 2647435461];
for (const want of ref) { checks++; const got = r.nextU32(); if (got !== want) { fails++; console.log(`FAIL rng ${got} != ${want}`); } }

// profile lengths match Python
const lens = { en50530_high: 15934, en50530_low: 19300, clouds: 3560, shading: 4000, steady: 1500 };
for (const [k, n] of Object.entries(lens)) { checks++; if (X.getProfile(k).length !== n) { fails++; console.log(`FAIL profile ${k} length`); } }

// trackers: closed loop on the shading+clouds slice, decision for decision
const eta = new X.EtaTable(ETA_TABLE);
const oracle = new X.MppOracle();
const short = X.shading().slice(0, 1500).concat(X.clouds().slice(0, 1500));
for (const [key, want] of Object.entries(fx.mppt)) {
  const t = X.makeTracker(key, want.params);
  for (const [k, v] of Object.entries(want.params)) { checks++; if (X.makeTracker(key)[k] !== v) { fails++; console.log(`FAIL default ${key}.${k}`); } }
  const res = X.run(t, short, { seed: 11, eta, oracle, recordEvery: 50 });
  close(res.eta_mppt, want.eta_mppt, 1e-12, `${key} eta_mppt`);
  close(res.eta_sys, want.eta_sys, 1e-12, `${key} eta_sys`);
  // the fixture's traces are rounded to 3 decimals (JSON size), so allow half a unit of the last place;
  // a diverging decision would differ by a whole perturbation step (0.2 V or more)
  const near = (a, b, what) => { checks++; if (!(Math.abs(a - b) <= 5.0001e-4)) { fails++; console.log(`FAIL ${what}: js=${a} py=${b}`); } };
  want.p.forEach((p, i) => near(res.trace.p[i], p, `${key} p[${i}]`));
  want.v.forEach((v, i) => near(res.trace.v[i], v, `${key} v[${i}]`));
}

// efficiency controls at fixed operating points
for (const op of fx.ops) {
  const [vin, vout, pout, kappa] = op.args;
  const got = EC.operatingPoint(vin, vout, pout, kappa);
  for (const k of Object.keys(op.loss)) close(got.loss[k], op.loss[k], 1e-12, `op ${vin}V ${pout}W loss.${k}`);
  checks++; if (JSON.stringify(got.fs.path) !== JSON.stringify(op.fs_path)) { fails++; console.log(`FAIL fs path ${vin} ${pout}`); }
  checks++; if (JSON.stringify(got.td.path) !== JSON.stringify(op.td_path)) { fails++; console.log(`FAIL td path ${vin} ${pout}`); }
  checks++; if (JSON.stringify(got.fs.finals) !== JSON.stringify(op.fs_finals)) { fails++; console.log(`FAIL fs finals ${vin} ${pout}`); }
  checks++; if (JSON.stringify(got.td.finals) !== JSON.stringify(op.td_finals)) { fails++; console.log(`FAIL td finals ${vin} ${pout}`); }
  checks++; if ((got.burst.f_burst ?? null) !== op.f_burst) { fails++; console.log(`FAIL burst ${vin} ${pout}`); }
}

// the stored benchmark uses the current default parameters
for (const [key, params] of Object.entries(CONTROL_BENCHMARK.params)) for (const [k, v] of Object.entries(params)) {
  checks++; if (X.makeTracker(key)[k] !== v) { fails++; console.log(`FAIL benchmark params ${key}.${k}`); }
}
console.log(fails ? `${fails}/${checks} control checks FAILED` : `${checks} control checks passed`);
process.exit(fails ? 1 : 0);
