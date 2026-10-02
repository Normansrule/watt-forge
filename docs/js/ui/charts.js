// charts.js -- dependency-free SVG charts with hover tooltips (line, donut, bar list).
// Colors come from CSS classes c1..c6 (validated categorical palette); text uses ink tokens.
import { s, h } from './ui.js';

function scale(d0, d1, r0, r1, log = false) {
  if (log) {
    const a = Math.log10(d0), b = Math.log10(d1);
    return (x) => r0 + ((Math.log10(x) - a) / (b - a)) * (r1 - r0);
  }
  return (x) => r0 + ((x - d0) / (d1 - d0)) * (r1 - r0);
}
function niceTicks(lo, hi, n = 5) {
  const span = hi - lo;
  const step0 = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => span / x <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9 * span; v += step) out.push(+v.toPrecision(10));
  return out;
}
function logTicks(lo, hi) {
  const out = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) { const v = Math.pow(10, e); if (v >= lo * 0.999 && v <= hi * 1.001) out.push(v); }
  return out;
}

/**
 * lineChart(el, opts)
 * opts.series: [{name, cls, pts: [[x,y],...]}]; opts.x/y: {min,max,label,fmt,log}
 * opts.zones: [{x0,x1,label}] shaded bands; opts.target: [[x,y]] dashed line; opts.marks: [{x,y,cls,label}]
 */
export function lineChart(el, opts) {
  el.textContent = '';
  el.classList.add('chart');
  const W = opts.width || 720, H = opts.height || 320;
  const m = { l: 56, r: 18, t: opts.title ? 30 : 12, b: 44 };
  const all = opts.series.flatMap((sr) => sr.pts).concat(opts.target || []);
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  const xmin = opts.x?.min ?? Math.min(...xs), xmax = opts.x?.max ?? Math.max(...xs);
  let ymin = opts.y?.min ?? Math.min(...ys), ymax = opts.y?.max ?? Math.max(...ys);
  if (ymax - ymin < 1e-12) { ymin -= 1; ymax += 1; }
  const X = scale(xmin, xmax, m.l, W - m.r, opts.x?.log), Y = scale(ymin, ymax, H - m.b, m.t, opts.y?.log);
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': opts.aria || opts.title || 'chart' });
  if (opts.title) svg.append(s('text', { class: 'title', x: m.l, y: 18, text: opts.title }));
  for (const z of opts.zones || []) {
    svg.append(s('rect', { class: 'zone', x: X(z.x0), y: m.t, width: Math.max(0, X(z.x1) - X(z.x0)), height: H - m.b - m.t }));
    if (z.label) svg.append(s('text', { class: 'lbl', x: (X(z.x0) + X(z.x1)) / 2, y: m.t + 12, 'text-anchor': 'middle', text: z.label }));
  }
  const g = s('g', { class: 'grid' });
  const xt = opts.x?.log ? logTicks(xmin, xmax) : niceTicks(xmin, xmax, opts.x?.ticks || 8);
  const yt = opts.y?.log ? logTicks(ymin, ymax) : niceTicks(ymin, ymax, opts.y?.ticks || 5);
  const ax = s('g', { class: 'axis' });
  const xf = opts.x?.fmt || ((v) => String(v)), yf = opts.y?.fmt || ((v) => String(v));
  for (const v of yt) { g.append(s('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) })); ax.append(s('text', { x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end', text: yf(v) })); }
  for (const v of xt) { ax.append(s('text', { x: X(v), y: H - m.b + 16, 'text-anchor': 'middle', text: xf(v) })); }
  g.append(s('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }));
  svg.append(g, ax);
  if (opts.x?.label) svg.append(s('text', { class: 'lbl', x: (m.l + W - m.r) / 2, y: H - 8, 'text-anchor': 'middle', text: opts.x.label }));
  if (opts.y?.label) svg.append(s('text', { class: 'lbl', x: 14, y: (m.t + H - m.b) / 2, transform: `rotate(-90 14 ${(m.t + H - m.b) / 2})`, 'text-anchor': 'middle', text: opts.y.label }));
  const path = (pts) => pts.filter((p) => isFinite(p[1])).map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(Math.min(Math.max(p[1], ymin), ymax)).toFixed(1)}`).join('');
  if (opts.target) svg.append(s('path', { class: 'target', d: path(opts.target) }));
  for (const sr of opts.series) {
    svg.append(s('path', { class: `line ${sr.cls}`, d: path(sr.pts), ...(sr.step ? {} : {}) }));
    if (sr.endDot !== false && sr.pts.length) {
      const [lx, ly] = sr.pts[sr.pts.length - 1];
      if (ly >= ymin && ly <= ymax) svg.append(s('circle', { class: `dot ${sr.cls}`, cx: X(lx), cy: Y(ly), r: 4 }));
    }
  }
  for (const mk of opts.marks || []) {
    svg.append(s('circle', { class: `dot ${mk.cls || 'c2'}`, cx: X(mk.x), cy: Y(mk.y), r: mk.r || 5 }));
    if (mk.label) svg.append(s('text', { class: 'lbl', x: X(mk.x) + 8, y: Y(mk.y) - 8, text: mk.label }));
  }
  // hover layer
  const cross = s('line', { class: 'cross', y1: m.t, y2: H - m.b, visibility: 'hidden' });
  const hit = s('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' });
  svg.append(cross, hit);
  el.append(svg);
  const tip = h('div', { class: 'tip', hidden: true });
  el.append(tip);
  if (opts.series.length > 1 || opts.legend) {
    const items = opts.series.map((sr) => h('span', {}, h('span', { class: `sw ${sr.cls}` }), sr.name));
    if (opts.target) items.push(h('span', {}, h('span', { class: 'dash' }), 'target'));
    el.append(h('div', { class: 'legend' }, items));
  }
  const move = (evt) => {
    const r = svg.getBoundingClientRect();
    const px = ((evt.clientX - r.left) / r.width) * W;
    let best = null;
    for (const sr of opts.series) for (const p of sr.pts) {
      const d = Math.abs(X(p[0]) - px);
      if (!best || d < best.d) best = { d, x: p[0] };
    }
    if (!best) return;
    cross.setAttribute('x1', X(best.x)); cross.setAttribute('x2', X(best.x)); cross.setAttribute('visibility', 'visible');
    tip.textContent = '';
    tip.append(h('div', { text: (opts.x?.label || 'x') + ': ' + xf(best.x) }));
    for (const sr of opts.series) {
      const p = sr.pts.reduce((a, b) => (Math.abs(b[0] - best.x) < Math.abs(a[0] - best.x) ? b : a), sr.pts[0]);
      if (p && Math.abs(p[0] - best.x) < 1e-9 * Math.max(1, Math.abs(best.x)) + 1e-12) tip.append(h('div', {}, h('span', { class: `sw ${sr.cls}` }), ` ${sr.name}: ${(opts.tipFmt || yf)(p[1], sr, p)}`));
    }
    tip.hidden = false;
    const left = ((X(best.x) / W) * r.width);
    tip.style.left = Math.min(left + 12, r.width - tip.offsetWidth - 4) + 'px';
    tip.style.top = '8px';
  };
  hit.addEventListener('pointermove', move);
  hit.addEventListener('pointerleave', () => { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); });
  return { X, Y, svg };
}

/** donut(el, items [{name, value, cls}], {center, sub}) */
export function donut(el, items, opts = {}) {
  el.textContent = '';
  el.classList.add('chart', 'donut');
  const W = 240, R = 100, r0 = 62, cx = 120, cy = 110;
  const svg = s('svg', { viewBox: `0 0 ${W} 225`, role: 'img', 'aria-label': opts.aria || 'loss budget donut' });
  const total = items.reduce((a, b) => a + Math.max(b.value, 0), 0) || 1;
  let a0 = -Math.PI / 2;
  const tip = h('div', { class: 'tip', hidden: true });
  for (const it of items) {
    const frac = Math.max(it.value, 0) / total;
    if (frac <= 0) continue;
    const a1 = a0 + frac * 2 * Math.PI;
    const gap = Math.min(0.012, frac * Math.PI);
    const s0 = a0 + gap, s1 = a1 - gap;
    const large = s1 - s0 > Math.PI ? 1 : 0;
    const p = (a, rr) => `${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`;
    const d = frac > 0.9999
      ? `M${cx},${cy - R} A${R},${R} 0 1 1 ${cx - 0.01},${cy - R} L${cx - 0.01},${cy - r0} A${r0},${r0} 0 1 0 ${cx},${cy - r0} Z`
      : `M${p(s0, R)} A${R},${R} 0 ${large} 1 ${p(s1, R)} L${p(s1, r0)} A${r0},${r0} 0 ${large} 0 ${p(s0, r0)} Z`;
    const seg = s('path', { d, class: it.cls });
    seg.addEventListener('pointermove', (evt) => {
      const r = el.getBoundingClientRect();
      tip.textContent = `${it.name}: ${it.value.toFixed(3)} W (${(100 * frac).toFixed(1)} %)`;
      tip.hidden = false;
      tip.style.left = Math.min(evt.clientX - r.left + 10, r.width - 190) + 'px';
      tip.style.top = evt.clientY - r.top + 10 + 'px';
    });
    seg.addEventListener('pointerleave', () => { tip.hidden = true; });
    svg.append(seg);
    a0 = a1;
  }
  svg.append(s('text', { x: cx, y: cy + 2, 'text-anchor': 'middle', class: 'title', 'font-size': '20', text: opts.center || '' }));
  svg.append(s('text', { x: cx, y: cy + 20, 'text-anchor': 'middle', class: 'lbl', text: opts.sub || '' }));
  el.append(svg, tip);
  if (opts.legend !== false) el.append(h('div', { class: 'legend' }, items.map((it) => h('span', {}, h('span', { class: `sw ${it.cls}` }), `${it.name} ${it.value.toFixed(2)} W`))));
}

/** barList(el, items [{name, value, cls}], unit) : sorted horizontal bars with values at the tip. */
export function barList(el, items, unit = 'W', max = null) {
  el.textContent = '';
  const mx = max ?? Math.max(...items.map((i) => i.value), 1e-12);
  for (const it of items) {
    const bar = h('div', { class: `bar ${it.cls || 'c1'}` });
    bar.style.width = Math.max(0.5, (100 * it.value) / mx) + '%';
    el.append(h('div', { class: 'barrow' }, h('span', { text: it.name }), h('div', { class: 'track' }, bar), h('span', { class: 'val', text: `${it.value.toFixed(3)} ${unit}` })));
  }
}
