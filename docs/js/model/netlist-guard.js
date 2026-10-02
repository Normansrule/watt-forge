// netlist-guard.js -- reject SPICE netlists that could escape the simulator sandbox.
// Same rules as watt_forge/spice.py::check_netlist and desktop/netlist-guard (Rust);
// tests/fixtures/guard_cases.json is checked against all three.
// In the browser this is only feedback: the desktop app re-checks in Rust before ngspice runs.

export const MAX_BYTES = 256 * 1024;
export const MAX_LINES = 20000;
export const MAX_TRAN_POINTS = 5_000_000;
const ALLOWED_ELEMENTS = new Set('RCLVISDEGFHBKXMQJ');
const ALLOWED_DOT = new Set(['.model', '.tran', '.ic', '.param', '.meas', '.measure', '.option', '.options', '.end', '.title',
  '.subckt', '.ends', '.global', '.temp', '.op', '.dc', '.ac', '.save', '.func', '.nodeset']);
const FORBIDDEN_DOT = new Set(['.control', '.endc', '.include', '.inc', '.lib', '.endl', '.exec', '.csparam']);
const FORBIDDEN = /(^|[^a-z0-9_])(shell|system|exec|wrdata|write|wrs2p|load|source|cd|setcs|codemodel|pre_osdi|osdi)(?![a-z0-9_])/;
const SUFFIX = { t: 1e12, g: 1e9, meg: 1e6, k: 1e3, m: 1e-3, u: 1e-6, n: 1e-9, p: 1e-12, f: 1e-15 };

export class NetlistRejected extends Error {}

export function parseSpiceNumber(tok) {
  const m = /^([+-]?\d*\.?\d+(?:e[+-]?\d+)?)(meg|[tgkmunpf])?[a-z]*$/.exec(String(tok).trim().toLowerCase());
  if (!m) throw new NetlistRejected(`not a number: ${tok}`);
  return parseFloat(m[1]) * (SUFFIX[m[2] || ''] ?? 1);
}

/** Returns a list of warnings; throws NetlistRejected on any violation. */
export function checkNetlist(text) {
  const warnings = [];
  if (new TextEncoder().encode(text).length > MAX_BYTES) throw new NetlistRejected('netlist too large');
  if (text.includes('\0')) throw new NetlistRejected('binary content');
  const lines = text.split(/\r\n|\r|\n/);
  if (text.endsWith('\n')) lines.pop();
  if (lines.length > MAX_LINES) throw new NetlistRejected('too many lines');
  for (let i = 1; i < lines.length; i++) { // the first line is the title in SPICE
    const n = i + 1;
    const line = lines[i].trim();
    if (!line || line.startsWith('*') || line.startsWith(';')) continue;
    const cont = line.startsWith('+');
    const body = cont ? line.slice(1) : line;
    const low = body.toLowerCase();
    if (FORBIDDEN.test(low)) throw new NetlistRejected(`line ${n}: forbidden command`);
    if (low.startsWith('.')) {
      const word = low.split(/\s+/)[0];
      if (FORBIDDEN_DOT.has(word)) throw new NetlistRejected(`line ${n}: ${word} is not allowed`);
      if (!ALLOWED_DOT.has(word)) throw new NetlistRejected(`line ${n}: unknown dot command ${word}`);
      if (word === '.tran') {
        const t = low.split(/\s+/);
        let step, stop;
        try { step = parseSpiceNumber(t[1]); stop = parseSpiceNumber(t[2]); } catch { throw new NetlistRejected(`line ${n}: malformed .tran`); }
        if (step <= 0 || stop / step > MAX_TRAN_POINTS) throw new NetlistRejected(`line ${n}: .tran asks for too many points`);
      }
      continue;
    }
    if (cont) continue;
    if (!ALLOWED_ELEMENTS.has(body[0].toUpperCase())) throw new NetlistRejected(`line ${n}: element type '${body[0]}' not allowed`);
  }
  if (!lines.some((l) => l.trim().toLowerCase() === '.end')) warnings.push('no .end card (added automatically)');
  return warnings;
}

/** Pull `name = value` measurement lines out of ngspice batch output. */
export function parseMeasurements(out) {
  const res = {};
  for (const line of String(out).split(/\r?\n/)) {
    const m = /^\s*([a-z_][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)/.exec(line);
    if (m) { const v = parseFloat(m[2]); if (Number.isFinite(v)) res[m[1]] = v; }
  }
  return res;
}
