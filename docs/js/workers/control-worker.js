// control-worker.js -- runs MPPT benchmarks off the main thread for the Control Lab.
// Message in:  { id, profile, keys, seeds, noise, sigmaV, sigmaI, params: {key: {...}}, recordEvery }
// Messages out: { id, progress: 0..1 } ... then { id, done: true, results: {key: {eta_mppt, eta_sys, e_lost_J, runs, trace}} }
import * as X from '../model/mppt.js';
import { ETA_TABLE } from '../data/eta_table.js';

const eta = new X.EtaTable(ETA_TABLE);
const oracle = new X.MppOracle();
const profiles = new Map();

self.onmessage = (ev) => {
  const m = ev.data || {};
  try {
    if (!profiles.has(m.profile)) profiles.set(m.profile, X.getProfile(m.profile));
    const prof = profiles.get(m.profile);
    const keys = m.keys || Object.keys(X.ALGORITHMS);
    const seeds = m.seeds && m.seeds.length ? m.seeds : [7];
    const total = keys.length * seeds.length;
    const results = {};
    let done = 0;
    for (const key of keys) {
      const runs = [];
      for (const seed of seeds) {
        const tracker = X.makeTracker(key, (m.params && m.params[key]) || {});
        const r = X.run(tracker, prof, { seed, eta, oracle, noise: m.noise !== false, sigmaV: m.sigmaV, sigmaI: m.sigmaI,
          recordEvery: seed === seeds[0] ? (m.recordEvery || 0) : 0 });
        runs.push(r);
        done += 1;
        self.postMessage({ id: m.id, progress: done / total });
      }
      const mean = (f) => runs.reduce((a, r) => a + f(r), 0) / runs.length;
      results[key] = { eta_mppt: mean((r) => r.eta_mppt), eta_sys: mean((r) => r.eta_sys), e_lost_J: mean((r) => r.e_lost_J),
        e_mpp_J: runs[0].e_mpp_J, min: Math.min(...runs.map((r) => r.eta_mppt)), max: Math.max(...runs.map((r) => r.eta_mppt)),
        trace: runs[0].trace || null };
    }
    self.postMessage({ id: m.id, done: true, results });
  } catch (e) {
    self.postMessage({ id: m.id, error: String(e && e.message || e) });
  }
};
