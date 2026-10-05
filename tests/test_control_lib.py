"""Control library: C == Python decision for decision, behaviour checks, efficiency controls."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from watt_forge import pv
from watt_forge.control import bench, efficiency as E, mppt as M, profiles as PR
from watt_forge.control.rng import XorShift32

ROOT = Path(__file__).resolve().parents[1]
CDIR = ROOT / "hardware" / "flagship" / "control"
KIND = {k: n for n, k in enumerate(["po", "vspo", "inc", "vsinc", "focv", "esc", "pso", "scan"])}
SHORT = PR.get("shading")[:1500] + PR.get("clouds")[:1500]


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not installed")
    exe = tmp_path_factory.mktemp("c") / "wf_mppt_harness"
    subprocess.run(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(exe),
                    str(CDIR / "wf_mppt.c"), str(CDIR / "wf_mppt_harness.c")], check=True)
    return exe


@pytest.fixture(scope="module")
def shared():
    panel = pv.Panel()
    return panel, bench.MppOracle(panel), bench.EtaTable()


def test_rng_reference_values():
    r = XorShift32(1)
    assert [r.next_u32() for _ in range(3)] == [270369, 67634689, 2647435461]


@pytest.mark.parametrize("key", M.keys())
def test_c_tracker_matches_python(harness, shared, key):
    panel, oracle, eta = shared
    tr = M.make(key)
    log = []
    bench.run(tr, SHORT, seed=5, oracle=oracle, eta=eta, panel=panel, log=log)
    args = [str(harness), "mppt", str(KIND[key]), "12345"] + [f"{k}={v!r}" for k, v in tr.params().items()]
    stdin = "".join(f"R {e[1]!r}\n" if e[0] == "R" else f"U {e[1]!r} {e[2]!r}\n" for e in log)
    out = subprocess.run(args, input=stdin, capture_output=True, text=True, check=True).stdout.split("\n")
    bad = []
    for n, (e, line) in enumerate(zip(log, out)):
        vref, op = line.split()
        want_vref, want_open = (e[2], e[3]) if e[0] == "R" else (e[3], e[4])
        if float(vref) != want_vref or int(op) != int(want_open):
            bad.append((n, e, line))
    assert len(log) > 100
    assert not bad, bad[:3]


def test_c_hillclimb_matches_python(harness):
    costs = [5.0, 4.2, 3.9, 3.7, 3.8, 4.4, None, 6.0]
    res = E.online_search(costs, start=0, updates=80, seed=9)
    rng = XorShift32(9)
    hc = E.HillClimb(len(costs), 0)
    idx, feed = 0, []
    for _ in range(80):
        c = costs[idx]
        c = 1e9 if c is None else c + 0.03 * rng.normal()
        feed.append(c)
        idx = hc.update(c)
    out = subprocess.run([str(harness), "hc", str(len(costs)), "0", "0.02", "10"], input="".join(f"{c!r}\n" for c in feed),
                         capture_output=True, text=True, check=True).stdout.split()
    assert [int(x) for x in out] == res["path"][1:]
    assert res["final"] == 3          # it finds the minimum


def test_global_trackers_escape_local_maximum(shared):
    panel, oracle, eta = shared
    prof = PR.get("shading")
    local = bench.run(M.make("po"), prof, oracle=oracle, eta=eta, panel=panel)["eta_mppt"]
    for key in ("pso", "scan"):
        assert bench.run(M.make(key), prof, oracle=oracle, eta=eta, panel=panel)["eta_mppt"] > local + 0.1


@pytest.mark.parametrize("key", M.keys())
def test_every_tracker_converges_in_steady_light(shared, key):
    panel, oracle, eta = shared
    r = bench.run(M.make(key), PR.get("steady"), oracle=oracle, eta=eta, panel=panel)
    assert r["eta_mppt"] > 0.97, r["eta_mppt"]
    assert r["eta_sys"] < r["eta_mppt"]       # conversion losses come on top


def test_bench_energy_bookkeeping(shared):
    panel, oracle, eta = shared
    r = bench.run(M.make("po"), PR.get("steady")[:500], oracle=oracle, eta=eta, panel=panel)
    assert r["e_lost_J"] == pytest.approx(r["e_mpp_J"] - r["e_pv_J"])
    assert 0.0 < r["e_batt_J"] < r["e_pv_J"] <= r["e_mpp_J"] * 1.0000001


def test_eta_table_matches_model():
    from watt_forge.flagship import model
    t = bench.EtaTable()
    r = model.best(36.0, 48.0, 200.0)
    pin = 200.0 / r["eta"]
    assert t(36.0, pin) == pytest.approx(r["eta"], abs=2e-3)


def test_adaptive_frequency_finds_the_optimum():
    for vin, pout in ((36.0, 300.0), (24.0, 200.0), (56.0, 400.0), (20.0, 5.0)):
        op = E.operating_point(vin, 48.0, pout)
        assert op["fs"]["online"] == op["fs"]["optimum"]      # the most common landing point
        assert op["fs"]["hit_rate"] >= 0.5
        assert op["loss"]["fs"] <= op["loss"]["base"] + 1e-12


def test_measurement_resolution_is_realistic():
    # 5 s of 20 ms ticks with the MPPT bench's per-tick sensor noise: about 25 mW at 40 V
    s = E.power_sigma(40.0, 21.0)
    assert 0.015 < s < 0.04
    assert s == pytest.approx(((21.0 / 40.0 * 0.02) ** 2 + (40.0 * 0.01) ** 2) ** 0.5 / 250 ** 0.5)


def test_bypass_pays_for_pinning_the_panel():
    # panel MPP 1.5 % above the battery: bypass must include (1/2) kappa dV^2 of mismatch
    op = E.operating_point(48.72, 48.0, 300.0, kappa=3.8)
    assert op["bypass_mismatch"] == pytest.approx(0.5 * 3.8 * 0.72 ** 2)


def test_burst_ripple_stays_small_signal():
    for vin, pout in ((16.0, 5.0), (40.0, 20.0)):
        b = E.burst(vin, 48.0, pout, E.kappa_estimate(vin, pout))
        assert not b["active"] or b["dv_pp"] <= E.BURST_MAX_RIPPLE * vin


def test_dead_time_tradeoff_has_an_interior_optimum():
    c = [x["loss"] for x in E.td_curve(36.0, 48.0, 300.0, 75e3)]
    i = min(range(len(c)), key=lambda k: c[k])
    assert 0 < i < len(c) - 1          # too short: hard Coss loss; too long: reverse conduction


def test_burst_mode_helps_only_at_light_load():
    m = pv.global_mpp([40.0] * 3, 30.0, pv.Panel())          # ~12 W of light
    k = E.pv_curvature(m["v"], 40.0, 30.0)
    light = E.operating_point(m["v"], 48.0, 10.0, kappa=k)
    assert light["loss"]["burst"] < 0.8 * light["loss"]["td"]
    heavy = E.operating_point(36.0, 48.0, 300.0, kappa=E.pv_curvature(37.6, 1000.0, 40.0))
    assert heavy["loss"]["burst"] == heavy["loss"]["td"]


def test_burst_respects_minimum_burst_length():
    b = E.burst(35.0, 48.0, 10.0, 0.1)
    assert b["active"] and b["delta"] / b["f_burst"] >= E.BURST_MIN_CYCLES / b["fs_burst"] * 0.999


def test_profiles_match_en50530_slopes():
    prof = PR.get("en50530_high")
    g = [e["g"][0] for e in prof]
    slopes = {round(abs(b - a) / PR.DT) for a, b in zip(g, g[1:]) if b != a}
    assert {10, 30, 50, 100} <= slopes
    assert min(g) == 300.0 and max(g) == 1000.0


def test_stored_benchmark_is_current():
    """data/control_benchmark.json must have been generated with the current tuned parameters."""
    doc = json.loads((ROOT / "data" / "control_benchmark.json").read_text())
    tuned = json.loads((ROOT / "data" / "mppt_tuned.json").read_text())["best"]
    for key, spec in tuned.items():
        assert doc["params"][key] == M.make(key).params(), key
        for name, val in spec["params"].items():
            assert getattr(M.make(key), name) == val, (key, name)
