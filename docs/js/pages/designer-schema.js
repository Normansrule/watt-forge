// designer-schema.js -- validation of untrusted design objects (imports and saved designs).
import { TOPOLOGIES } from '../model/topologies.js';
import { switching } from '../model/devices.js';

// ---- untrusted-input schema (import + saved designs)
const SCHEMA = {
  topology: (v) => TOPOLOGIES.some(([k]) => k === v),
  vin: [1, 1000], vout: [0.5, 1000], pout: [0.1, 1e5], fs_khz: [1, 1e4], ripple_frac: [0.05, 2],
  device: (v) => switching().some((d) => d.id === v), sync: (v) => typeof v === 'boolean', dcr_mohm: [0, 1000], n: [0.01, 100],
};
export function validateDesign(obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) throw new Error('Expected a JSON object.');
  const out = {};
  for (const [k, rule] of Object.entries(SCHEMA)) {
    if (!Object.hasOwn(obj, k)) throw new Error(`Missing field "${k}".`);
    const v = obj[k];
    if (typeof rule === 'function') { if (!rule(v)) throw new Error(`Field "${k}" has an unsupported value.`); out[k] = v; }
    else {
      if (typeof v !== 'number' || !isFinite(v) || v < rule[0] || v > rule[1]) throw new Error(`Field "${k}" must be a number between ${rule[0]} and ${rule[1]}.`);
      out[k] = v;
    }
  }
  for (const k of Object.keys(obj)) if (!Object.hasOwn(SCHEMA, k) && k !== 'name') throw new Error(`Unknown field "${k}".`);
  return out;
}

