// expr.js -- safe expression evaluator for user-entered formulas (the validator's target curve).
// Never uses eval/Function: tokenize -> shunting-yard -> RPN evaluation over a whitelist.
// Variables are passed explicitly; anything else is a parse error.

const FUNCS = Object.assign(Object.create(null), {
  sqrt: [1, Math.sqrt], abs: [1, Math.abs], exp: [1, Math.exp], ln: [1, Math.log], log10: [1, Math.log10],
  min: [2, Math.min], max: [2, Math.max], pow: [2, Math.pow], clamp: [3, (x, a, b) => Math.min(Math.max(x, a), b)],
});
const CONSTS = Object.assign(Object.create(null), { pi: Math.PI, e: Math.E });
// null-prototype maps: names like 'constructor' or '__proto__' must never resolve
const OPS = Object.assign(Object.create(null), { '+': [1, 'L'], '-': [1, 'L'], '*': [2, 'L'], '/': [2, 'L'], '^': [3, 'R'], 'neg': [4, 'R'] });
export const MAX_LEN = 200;

export function tokenize(src) {
  if (typeof src !== 'string' || src.length > MAX_LEN) throw new Error('expression too long');
  const out = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === ' ' || c === '\t') { i++; continue; }
    if (/[0-9.]/.test(c)) {
      const m = /^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i.exec(src.slice(i));
      if (!m) throw new Error('bad number at ' + i);
      out.push({ t: 'num', v: parseFloat(m[0]) });
      i += m[0].length; continue;
    }
    if (/[a-z_]/i.test(c)) {
      const m = /^[a-z_][a-z0-9_]*/i.exec(src.slice(i));
      out.push({ t: 'id', v: m[0].toLowerCase() });
      i += m[0].length; continue;
    }
    if ('+-*/^(),'.includes(c)) { out.push({ t: c }); i++; continue; }
    throw new Error(`unexpected character '${c}'`);
  }
  return out;
}

export function compile(src, vars) {
  const toks = tokenize(src);
  const rpn = [], st = [], argc = [];
  let prev = null;
  for (let k = 0; k < toks.length; k++) {
    const tk = toks[k];
    if (tk.t === 'num') rpn.push(tk);
    else if (tk.t === 'id') {
      if (Object.hasOwn(FUNCS, tk.v) && toks[k + 1] && toks[k + 1].t === '(') { st.push({ t: 'fn', v: tk.v }); }
      else if (vars.includes(tk.v)) rpn.push({ t: 'var', v: tk.v });
      else if (Object.hasOwn(CONSTS, tk.v)) rpn.push({ t: 'num', v: CONSTS[tk.v] });
      else throw new Error(`unknown name '${tk.v}' (allowed: ${vars.join(', ')}, ${Object.keys(FUNCS).join(', ')}, pi, e)`);
    } else if (tk.t === ',') {
      while (st.length && st[st.length - 1].t !== '(') rpn.push(st.pop());
      if (!argc.length) throw new Error('comma outside a function');
      argc[argc.length - 1]++;
    } else if (tk.t === '(') { st.push(tk); argc.push(1); }
    else if (tk.t === ')') {
      while (st.length && st[st.length - 1].t !== '(') rpn.push(st.pop());
      if (!st.length) throw new Error('unbalanced )');
      st.pop();
      const n = argc.pop();
      if (st.length && st[st.length - 1].t === 'fn') {
        const f = st.pop();
        if (FUNCS[f.v][0] !== n) throw new Error(`${f.v} takes ${FUNCS[f.v][0]} argument(s)`);
        rpn.push(f);
      }
    } else {
      let op = tk.t;
      const unary = op === '-' && (prev === null || ['(', ',', '+', '-', '*', '/', '^'].includes(prev.t));
      if (unary) op = 'neg';
      else if (op === '+' && (prev === null || ['(', ','].includes(prev.t))) { prev = tk; continue; }
      const [p1, a1] = OPS[op];
      while (st.length) {
        const top = st[st.length - 1];
        if (!OPS[top.t]) break;
        const [p2] = OPS[top.t];
        if ((a1 === 'L' && p1 <= p2) || (a1 === 'R' && p1 < p2)) rpn.push(st.pop()); else break;
      }
      st.push({ t: op });
    }
    prev = tk;
  }
  while (st.length) {
    const x = st.pop();
    if (x.t === '(') throw new Error('unbalanced (');
    rpn.push(x);
  }
  // validate stack depth once
  let depth = 0;
  for (const x of rpn) {
    if (x.t === 'num' || x.t === 'var') depth++;
    else if (x.t === 'neg') { if (depth < 1) throw new Error('syntax error'); }
    else if (x.t === 'fn') { const n = FUNCS[x.v][0]; if (depth < n) throw new Error('syntax error'); depth -= n - 1; }
    else { if (depth < 2) throw new Error('syntax error'); depth--; }
  }
  if (depth !== 1) throw new Error('syntax error');
  return (env) => {
    const s = [];
    for (const x of rpn) {
      if (x.t === 'num') s.push(x.v);
      else if (x.t === 'var') s.push(+env[x.v]);
      else if (x.t === 'neg') s.push(-s.pop());
      else if (x.t === 'fn') { const n = FUNCS[x.v][0]; const args = s.splice(s.length - n, n); s.push(FUNCS[x.v][1](...args)); }
      else {
        const b = s.pop(), a = s.pop();
        s.push(x.t === '+' ? a + b : x.t === '-' ? a - b : x.t === '*' ? a * b : x.t === '/' ? a / b : Math.pow(a, b));
      }
    }
    return s[0];
  };
}
