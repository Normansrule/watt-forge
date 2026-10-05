// ui.js -- small DOM helpers shared by every page (no dependencies).
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const SVGNS = 'http://www.w3.org/2000/svg';

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'text') el.textContent = v;
    else if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return el;
}

export function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    if (k === 'text') el.textContent = v;
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid) el.append(kid);
  return el;
}

// Engineering-number formatting: 4.7e-6 -> "4.7 u"
export function eng(x, unit = '', digits = 3) {
  if (x === null || x === undefined || !isFinite(x)) return '-';
  if (x === 0) return '0 ' + unit;
  const p = [[1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, ''], [1e-3, 'm'], [1e-6, 'u'], [1e-9, 'n'], [1e-12, 'p']];
  const a = Math.abs(x);
  for (const [f, pre] of p) if (a >= f * 0.9995) return `${(x / f).toPrecision(digits).replace(/\.?0+$/, '')} ${pre}${unit}`;
  return `${x.toPrecision(digits)} ${unit}`;
}
export const pct = (x, d = 2) => `${(100 * x).toFixed(d)} %`;
export const watts = (x) => (Math.abs(x) >= 10 ? x.toFixed(1) : x.toFixed(3)) + ' W';

// Range slider bound to an <output>; returns a getter.
export function slider(id, fmt = (v) => v, onInput) {
  const el = document.getElementById(id);
  const out = document.querySelector(`output[for="${id}"]`);
  const upd = () => { if (out) out.textContent = fmt(+el.value); if (onInput) onInput(+el.value); };
  el.addEventListener('input', upd);
  upd();
  return () => +el.value;
}

// localStorage wrappers that never throw (private mode, blocked storage)
export const store = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem('wattforge:' + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem('wattforge:' + key, JSON.stringify(value)); return true; } catch { return false; } },
};

export function debounce(fn, ms = 60) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// theme toggle (persisted per viewer)
function initTheme() {
  const saved = store.get('theme');
  if (saved) document.documentElement.dataset.theme = saved;
  const btn = document.querySelector('.theme-btn');
  if (!btn) return;
  const label = () => { btn.textContent = document.documentElement.dataset.theme === 'dark' ? 'Light theme' : 'Dark theme'; };
  label();
  btn.addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    store.set('theme', document.documentElement.dataset.theme);
    label();
  });
}
initTheme();

// Installable web app: register the offline service worker (served over HTTPS or localhost only;
// skipped inside the desktop app, which already ships every file).
if ('serviceWorker' in navigator && !globalThis.__TAURI__ && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  navigator.serviceWorker.register(new URL('../../sw.js', import.meta.url), { scope: new URL('../../', import.meta.url).pathname })
    .catch(() => { /* offline support is optional */ });
}

export const LOSS_GROUPS = [
  ['Switch conduction', ['switch_conduction', 'cond_switch', 'cond_diode']],
  ['Switching', ['coss', 'coss_hard', 'overlap', 'coss_hysteresis', 'loop_ringing', 'dead_time', 'reverse_recovery', 'gate', 'leakage_clamp']],
  ['Inductor', ['inductor_dcr', 'inductor_ac', 'inductor_core']],
  ['Capacitors', ['cfly_esr', 'cin_cout_esr', 'cap_esr']],
  ['Sense, copper, disconnect', ['shunts', 'pcb_copper', 'bds_disconnect', 'bds_path']],
  ['Housekeeping', ['aux']],
];
export const LOSS_NAMES = {
  switch_conduction: 'Switch conduction (I²R)', cond_switch: 'Switch conduction (I²R)', cond_diode: 'Diode conduction (Vf·I)',
  coss: 'Output-capacitance (Coss) turn-on', coss_hard: 'Output-capacitance (Coss) turn-on', overlap: 'V-I overlap',
  coss_hysteresis: 'Coss hysteresis', loop_ringing: 'Loop ringing', dead_time: 'Dead-time reverse conduction',
  reverse_recovery: 'Reverse recovery (Qrr)', gate: 'Gate drive', leakage_clamp: 'Leakage clamp', inductor_dcr: 'Inductor copper (DCR)',
  inductor_ac: 'Inductor AC resistance', inductor_core: 'Inductor core (iGSE)', cfly_esr: 'Flying-cap ESR', cin_cout_esr: 'Input/output cap ESR',
  cap_esr: 'Capacitor ESR', shunts: 'Current shunts', pcb_copper: 'PCB copper', bds_disconnect: 'Bidirectional-GaN disconnect',
  bds_path: 'Bypass path (2 BDS)', aux: 'Housekeeping (MCU, drivers)',
};
export function groupLosses(losses) {
  return LOSS_GROUPS.map(([name, keys], i) => ({ name, cls: 'c' + (i + 1), value: keys.reduce((a, k) => a + (losses[k] || 0), 0) }));
}

// Link to a file in the GitHub repository (the Pages site only serves docs/).
// On <user>.github.io/<repo>/ the owner and repo are derived from the URL; elsewhere
// (local preview, desktop app) we fall back to a relative path from docs/.
export function repoLink(path) {
  const host = location.hostname;
  if (host.endsWith('.github.io')) {
    const user = host.replace('.github.io', '');
    const repo = location.pathname.split('/').filter(Boolean)[0] || '';
    if (repo) return `https://github.com/${user}/${repo}/blob/main/${path}`;
  }
  return null;
}
// a[data-gh="releases"] -> https://github.com/<user>/<repo>/releases (repo root when empty)
function wireGhLinks(root = document) {
  const host = location.hostname;
  const repo = location.pathname.split('/').filter(Boolean)[0] || '';
  for (const a of root.querySelectorAll('a[data-gh]')) {
    if (host.endsWith('.github.io') && repo) a.href = `https://github.com/${host.replace('.github.io', '')}/${repo}${a.dataset.gh ? '/' + a.dataset.gh : ''}`;
    else { a.removeAttribute('href'); a.title = 'On the GitHub repository page'; }
  }
}
wireGhLinks();

export function wireRepoLinks(root = document) {
  for (const a of root.querySelectorAll('a[data-repo]')) {
    const url = repoLink(a.dataset.repo);
    if (url) a.href = url;
    else { a.removeAttribute('href'); a.title = `In the repository: ${a.dataset.repo}`; }
  }
}
