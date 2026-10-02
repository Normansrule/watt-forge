"""Device database access and derived switching quantities."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from . import losses

DATA = Path(__file__).resolve().parent.parent / "data" / "devices.json"


@dataclass(frozen=True)
class Device:
    id: str
    maker: str
    tech: str
    vds: float
    rds_typ_mohm: float
    rds_max_mohm: float
    rds_tc: float
    qg_nc: float
    qgd_nc: Optional[float]
    qoss_nc: float
    qoss_v: float
    qoss_exp: float
    qrr_nc: float
    vsd: Optional[float]
    vdrv: float
    vpl: Optional[float]
    rg_ohm: Optional[float]
    id_a: float
    package: str
    url: str
    verified: tuple = field(default_factory=tuple)
    notes: str = ""

    # ---- derived
    def rds(self, tj: float = 25.0, use_max: bool = True) -> float:
        """On-resistance [ohm] at junction temperature tj (linear tempco estimate)."""
        base = self.rds_max_mohm if use_max else self.rds_typ_mohm
        return base * 1e-3 * (1.0 + self.rds_tc * (tj - 25.0))

    def qoss(self, v: float) -> float:
        return losses.qoss_at(self.qoss_nc * 1e-9, self.qoss_v, v, self.qoss_exp)

    def eoss(self, v: float) -> float:
        return losses.eoss_from_qoss(self.qoss(v), v, self.qoss_exp)

    def qg(self) -> float:
        return self.qg_nc * 1e-9

    def qrr(self) -> float:
        return self.qrr_nc * 1e-9

    def t_overlap(self, turn_on: bool) -> float:
        """Estimated overlap time [s]: (Qgs2 + Qgd) ~ 1.5 Qgd divided by the plateau gate current."""
        if self.qgd_nc is None or self.vpl is None or self.rg_ohm is None:
            return 0.0
        return losses.overlap_time(1.5 * self.qgd_nc * 1e-9, self.vdrv, self.vpl, self.rg_ohm, turn_on)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["verified"] = list(self.verified)
        return d


@lru_cache(maxsize=1)
def _load() -> Dict[str, Device]:
    raw = json.loads(DATA.read_text())
    out: Dict[str, Device] = {}
    for d in raw["devices"]:
        d = dict(d)
        d.pop("coss_er_pf", None)
        d.pop("coss_tr_pf", None)
        d["verified"] = tuple(d.get("verified", ()))
        out[d["id"]] = Device(**d)
    return out


def get(device_id: str) -> Device:
    return _load()[device_id]


def all_devices() -> List[Device]:
    return list(_load().values())


def by_tech(tech: str) -> List[Device]:
    return [d for d in all_devices() if d.tech == tech]
