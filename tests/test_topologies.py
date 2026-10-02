"""Generic topology designer and the device database."""
import json
from pathlib import Path

import pytest

from watt_forge import devices, topologies


@pytest.mark.parametrize("top,vin,vout", [
    ("buck", 48, 12), ("boost", 24, 48), ("buck_boost", 48, 24), ("sepic", 24, 36),
    ("cuk", 24, 36), ("flyback", 48, 12), ("four_switch", 48, 24), ("four_switch", 24, 48), ("four_switch", 48, 48),
])
@pytest.mark.parametrize("sync", [True, False])
def test_designer_sane(top, vin, vout, sync):
    r = topologies.design(topology=top, vin=vin, vout=vout, pout=100, fs=200e3, sync=sync)
    assert 0.80 < r["eta"] < 1.0
    assert r["l"] > 0 and r["c_out"] > 0
    assert all(v >= 0 for v in r["losses"].values())
    assert r["total_loss"] == pytest.approx(sum(r["losses"].values()))


def test_designer_buck_matches_hand_calc():
    r = topologies.design(topology="buck", vin=48, vout=12, pout=120, fs=200e3, ripple_frac=0.3, device="EPC2302")
    assert r["il"] == pytest.approx(10.0)
    assert r["delta_i"] == pytest.approx(3.0)
    assert r["d"] == pytest.approx(0.25, abs=0.01)
    assert r["l"] == pytest.approx(15e-6, rel=0.05)


def test_sync_beats_diode_at_low_voltage():
    a = topologies.design(topology="buck", vin=12, vout=3.3, pout=30, fs=300e3, sync=True)
    b = topologies.design(topology="buck", vin=12, vout=3.3, pout=30, fs=300e3, sync=False)
    assert a["eta"] > b["eta"]


def test_gan_beats_silicon_on_switching_loss():
    g = topologies.design(topology="buck", vin=48, vout=12, pout=200, fs=500e3, device="EPC2302")
    s = topologies.design(topology="buck", vin=48, vout=12, pout=200, fs=500e3, device="CSD19536KTT")
    sw = lambda r: r["losses"]["coss_hard"] + r["losses"]["overlap"] + r["losses"].get("reverse_recovery", 0) + r["losses"]["gate"]  # noqa: E731
    assert sw(g) < 0.5 * sw(s)


def test_device_database_integrity():
    raw = json.loads((Path(__file__).resolve().parents[1] / "data" / "devices.json").read_text())
    ids = set()
    for d in raw["devices"]:
        assert d["id"] not in ids
        ids.add(d["id"])
        assert d["url"].startswith("https://")
        assert d["verified"], "every device lists which fields were checked against the datasheet"
        assert d["rds_max_mohm"] >= d["rds_typ_mohm"]
        if d["tech"].startswith("GaN"):
            assert d["qrr_nc"] == 0
    assert devices.get("EPC2361").rds(25) == pytest.approx(1.0e-3)
    assert devices.get("EPC2361").rds(100) > devices.get("EPC2361").rds(25)
