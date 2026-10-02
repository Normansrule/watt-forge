// topologies.js -- generic topology designer. Port of watt_forge/topologies.py.
import * as C from './core.js';
import * as D from './devices.js';

export const DEFAULTS = {
  topology: 'buck', vin: 48, vout: 12, pout: 100, fs: 200e3, ripple_frac: 0.3, vripple_frac: 0.01,
  device: 'EPC2302', sync: true, diode_vf: 0.55, diode_qc_nc: 30, dcr_mohm: 4, esr_in_mohm: 2, esr_out_mohm: 2,
  tj: 80, t_dead: 15e-9, n: 1, leakage_frac: 0.02, core: 'ferrite_generic', b_design: 0.3, energy_density: 1.5e3,
};

export const TOPOLOGIES = [
  ['buck', 'Buck'], ['boost', 'Boost'], ['buck_boost', 'Inverting buck-boost'], ['sepic', 'SEPIC'],
  ['cuk', 'Cuk'], ['flyback', 'Flyback'], ['four_switch', 'Four-switch buck-boost'],
];

function cellLosses(vsw, iv, ipk, dm, isw, di, fs, dev, s, sync) {
  const out = {};
  const r = D.rds(dev, s.tj);
  const i2m = dm * (isw * isw + (di * di) / 12);
  const i2s = (1 - dm) * (isw * isw + (di * di) / 12);
  const q = D.qoss(dev, vsw);
  out.cond_switch = r * i2m;
  if (sync) {
    out.cond_switch += r * i2s;
    let trcOn;
    if (iv > 0) {
      out.coss_hard = C.hardTurnOnHalfbridge(q, vsw, fs);
      out.overlap = 0.5 * vsw * iv * D.tOverlap(dev, true) * fs;
      trcOn = s.t_dead;
    } else {
      const res = C.zvsResidualFraction(iv, s.t_dead, q);
      out.coss_hard = q * vsw * res * res * fs;
      out.overlap = 0;
      trcOn = Math.max(0, s.t_dead - (2 * q) / Math.max(Math.abs(iv), 1e-12));
    }
    out.overlap += 0.5 * vsw * Math.abs(ipk) * D.tOverlap(dev, false) * fs;
    const trcOff = Math.max(0, s.t_dead - (2 * q) / Math.max(Math.abs(ipk), 1e-12));
    out.dead_time = (dev.vsd || 0) * (Math.abs(iv) * trcOn + Math.abs(ipk) * trcOff) * fs;
    out.reverse_recovery = iv > 0 ? C.reverseRecovery(D.qrr(dev), vsw, fs) : 0;
    out.gate = 2 * C.gateDrive(D.qg(dev), dev.vdrv, fs);
  } else {
    out.cond_diode = s.diode_vf * (1 - dm) * isw;
    out.coss_hard = D.eoss(dev, vsw) * fs + s.diode_qc_nc * 1e-9 * vsw * fs;
    out.overlap = 0.5 * vsw * (Math.max(iv, 0) * D.tOverlap(dev, true) + Math.abs(ipk) * D.tOverlap(dev, false)) * fs;
    out.gate = C.gateDrive(D.qg(dev), dev.vdrv, fs);
  }
  return out;
}

function add(a, b) { for (const k in b) a[k] = (a[k] || 0) + b[k]; }

export function design(spec = {}) {
  const s = { ...DEFAULTS };
  for (const k in spec) if (spec[k] !== undefined && spec[k] !== null) s[k] = spec[k];
  const top = s.topology;
  const vin = +s.vin, vout = Math.abs(+s.vout), pout = +s.pout, fs = +s.fs;
  const dev = typeof s.device === 'object' ? s.device : D.get(s.device);
  const sync = !!s.sync;
  const iout = pout / vout;
  const m = vout / vin;
  const mat = C.MATERIALS[s.core];
  const kst = C.steinmetzK(mat);
  let eta = 0.95, result = null;
  for (let it = 0; it < 3; it++) {
    const notes = [];
    const iin = pout / eta / vin;
    const lb = {};
    const inductors = [];
    let d, il, vsw, di, l, cOut, iCin, iCout;
    if (top === 'buck') {
      il = iout;
      d = Math.min((vout + il * (D.rds(dev, s.tj) + s.dcr_mohm * 1e-3)) / vin, 0.995);
      vsw = vin; di = s.ripple_frac * il;
      l = C.inductorForRipple('buck', vin, vout, d, di, fs);
      add(lb, cellLosses(vsw, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync));
      inductors.push([l, il, di, d]);
      cOut = C.outputCapForRipple('buck', iout, d, di, s.vripple_frac * vout, fs);
      iCin = Math.sqrt(Math.max(d * (il ** 2 + di ** 2 / 12) - (d * il) ** 2, 0));
      iCout = di / Math.sqrt(12);
    } else if (['boost', 'buck_boost', 'sepic', 'cuk', 'flyback'].includes(top)) {
      const n = top === 'flyback' ? +s.n : 1;
      let isw;
      if (top === 'boost') {
        d = 1 - (vin - iin * (D.rds(dev, s.tj) + s.dcr_mohm * 1e-3)) / vout; il = iin; vsw = vout; isw = il;
      } else if (top === 'flyback') {
        d = vout / n / (vin + vout / n); il = iin / d; vsw = vin + vout / n; isw = il;
      } else {
        d = vout / (vin + vout); il = iout / (1 - d); vsw = vin + vout; isw = top === 'buck_boost' ? il : iin + iout;
      }
      d = Math.min(Math.max(d, 0.001), 0.995);
      if (top === 'sepic' || top === 'cuk') {
        const di1 = s.ripple_frac * iin, di2 = s.ripple_frac * iout;
        inductors.push([(vin * d) / (di1 * fs), iin, di1, d], [(vin * d) / (di2 * fs), iout, di2, d]);
        di = di1 + di2;
      } else {
        di = s.ripple_frac * il;
        l = (vin * d) / (di * fs);
        inductors.push([l, il, di, d]);
      }
      add(lb, cellLosses(vsw, isw - di / 2, isw + di / 2, d, isw, di, fs, dev, s, sync));
      cOut = C.outputCapForRipple('boost', iout, d, di, s.vripple_frac * vout, fs);
      iCout = top !== 'cuk' ? Math.sqrt(Math.max(d * iout ** 2 + (1 - d) * (isw - iout) ** 2, 0)) : di / Math.sqrt(12);
      iCin = ['boost', 'sepic', 'cuk'].includes(top) ? di / Math.sqrt(12) : Math.sqrt(Math.max(d * il ** 2 - (d * il) ** 2, 0));
      if (top === 'flyback') {
        const ipk = il + di / 2;
        lb.leakage_clamp = 0.5 * s.leakage_frac * inductors[0][0] * ipk * ipk * fs;
        notes.push('Flyback leakage (clamp) loss uses leakage_frac of Lm; transformer winding AC loss not modelled.');
      }
    } else if (top === 'four_switch') {
      const r = D.rds(dev, s.tj);
      let mode;
      if (m < 0.95) {
        mode = 'buck'; il = iout;
        d = Math.min((vout + il * (2 * r + s.dcr_mohm * 1e-3)) / vin, 0.995);
        di = s.ripple_frac * il;
        l = C.inductorForRipple('buck', vin, vout, d, di, fs);
        add(lb, cellLosses(vin, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync));
        lb.cond_switch += r * (il * il + (di * di) / 12);
        iCin = Math.sqrt(Math.max(d * (il ** 2 + di ** 2 / 12) - (d * il) ** 2, 0));
        iCout = di / Math.sqrt(12);
      } else if (m > 1.05) {
        mode = 'boost'; il = iin;
        d = 1 - (vin - il * (2 * r + s.dcr_mohm * 1e-3)) / vout;
        di = s.ripple_frac * il;
        l = (vin * d) / (di * fs);
        add(lb, cellLosses(vout, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync));
        lb.cond_switch += r * (il * il + (di * di) / 12);
        iCin = di / Math.sqrt(12);
        iCout = Math.sqrt(Math.max(d * iout ** 2 + (1 - d) * (il - iout) ** 2, 0));
      } else {
        mode = 'buck-boost';
        d = m / (1 + m); il = iout / (1 - d); di = s.ripple_frac * il; l = (vin * d) / (di * fs);
        add(lb, cellLosses(vin, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync));
        add(lb, cellLosses(vout, il - di / 2, il + di / 2, d, il, di, fs, dev, s, sync));
        iCin = Math.sqrt(Math.max(d * il ** 2 - (d * il) ** 2, 0));
        iCout = Math.sqrt(Math.max(d * iout ** 2 + (1 - d) * (il - iout) ** 2, 0));
      }
      notes.push(`four-switch operating in ${mode} mode`);
      inductors.push([l, il, di, d]);
      cOut = C.outputCapForRipple(mode === 'buck' ? 'buck' : 'boost', iout, d, di, s.vripple_frac * vout, fs);
      vsw = Math.max(vin, vout);
    } else {
      throw new Error('unknown topology ' + top);
    }
    lb.inductor_dcr = 0;
    lb.inductor_core = 0;
    for (const [lx, ilx, dix, dx] of inductors) {
      lb.inductor_dcr += s.dcr_mohm * 1e-3 * (ilx * ilx + (dix * dix) / 12);
      const ipk = Math.abs(ilx) + dix / 2;
      const vol = (lx * ipk * ipk) / (2 * s.energy_density);
      const dbpp = (s.b_design * dix) / Math.max(ipk, 1e-9);
      lb.inductor_core += C.igseTriangular(kst, mat.alpha, mat.beta, fs, dbpp, dx) * vol;
    }
    lb.cap_esr = s.esr_in_mohm * 1e-3 * iCin ** 2 + s.esr_out_mohm * 1e-3 * iCout ** 2;
    const total = Object.values(lb).reduce((a, b) => a + b, 0);
    eta = pout / (pout + total);
    const valley = inductors[0][1] - inductors[0][2] / 2;
    const ccm = valley > 0;
    if (!ccm && sync) notes.push('Valley current is negative: forced CCM (synchronous rectifier conducts backwards; helps ZVS).');
    else if (!ccm) notes.push('Valley current below zero: a diode converter would enter DCM; this CCM estimate is not valid.');
    result = {
      topology: top, sync, device: dev.id, d, m, fs, vin, vout, pout, iin: pout / eta / vin, iout,
      il: inductors[0][1], delta_i: inductors[0][2], l: inductors[0][0], l2: inductors.length > 1 ? inductors[1][0] : null,
      c_out: cOut, v_switch: vsw, losses: lb, total_loss: total, eta, k: C.kParam(inductors[0][0], (vout * vout) / pout, fs), ccm, notes,
    };
  }
  return result;
}
