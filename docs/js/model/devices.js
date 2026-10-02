// devices.js -- device helpers over the generated database (docs/js/data/devices.js).
import { DEVICES } from '../data/devices.js';
import { qossAt, eossFromQoss, overlapTime } from './core.js';

export const byId = Object.fromEntries(DEVICES.map((d) => [d.id, d]));
export const get = (id) => {
  const d = byId[id];
  if (!d) throw new Error('unknown device ' + id);
  return d;
};
export const rds = (d, tj = 25, useMax = true) => (useMax ? d.rds_max_mohm : d.rds_typ_mohm) * 1e-3 * (1 + d.rds_tc * (tj - 25));
export const qoss = (d, v) => qossAt(d.qoss_nc * 1e-9, d.qoss_v, v, d.qoss_exp);
export const eoss = (d, v) => eossFromQoss(qoss(d, v), v, d.qoss_exp);
export const qg = (d) => d.qg_nc * 1e-9;
export const qrr = (d) => d.qrr_nc * 1e-9;
export function tOverlap(d, turnOn) {
  if (d.qgd_nc == null || d.vpl == null || d.rg_ohm == null) return 0;
  return overlapTime(1.5 * d.qgd_nc * 1e-9, d.vdrv, d.vpl, d.rg_ohm, turnOn);
}
export const switching = () => DEVICES.filter((d) => d.tech !== 'GaN-BDS');
