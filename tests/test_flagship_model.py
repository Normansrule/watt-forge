"""Flagship analytic model: waveform physics and design constraints."""
import pytest

from watt_forge.flagship import model, pwm
from watt_forge.flagship.params import Params


P = Params()


def test_three_level_ripple_formula():
    # 3-level buck, D > 0.5: dI = (Vin - Vout)(D - 1/2) Ts / L  (node toggles between Vin/2 and Vin at 2 fs)
    vin, vout, fs, l = 56.0, 48.0, 100e3, 4.7e-6
    d = vout / vin
    segs, edges = pwm.build(d, 0.0, 0.0, 1 / fs, True, False)
    w = pwm.ideal_ripple(vin, vout, l, segs, edges, 1 / fs)
    assert w.ripple_pp() == pytest.approx((vin - vout) * (d - 0.5) / fs / l, rel=1e-9)
    # D < 0.5: dI = (Vin/2 - Vout) D Ts / L
    vin, vout = 60.0, 12.0
    d = vout / vin
    segs, edges = pwm.build(d, 0.0, 0.0, 1 / fs, True, False)
    w = pwm.ideal_ripple(vin, vout, l, segs, edges, 1 / fs)
    assert w.ripple_pp() == pytest.approx((vin / 2 - vout) * d / fs / l, rel=1e-9)
    # a two-level buck at the same point would ripple (Vin - Vout) D (1-D)... 3-level is 4x smaller at D=0.5
    two_level = (vin - 30.0) * 0.5 / fs / l
    segs, edges = pwm.build(0.5, 0.0, 0.0, 1 / fs, True, False)
    w = pwm.ideal_ripple(60.0, 30.0, l, segs, edges, 1 / fs)
    assert w.ripple_pp() == pytest.approx(0.0, abs=1e-12)  # node sits at Vin/2: the 2:1 SC point
    assert two_level > 0


def test_sc_region_is_the_sweet_spot():
    # At Vin = Vout/2 the boost leg runs at D = 0.5: near-zero ripple -> soft-charged 1:2 SC stage
    r = model.best(24.0, 48.0, 300.0, P)
    assert "SC" in r["label"]
    assert r["ripple_pp"] < 0.5
    # neighbours at the same power have much more ripple
    r2 = model.best(30.0, 48.0, 300.0, P)
    assert r2["ripple_pp"] > 5 * r["ripple_pp"]


def test_mode_selection():
    assert model.best(56.0, 48.0, 300.0, P)["mode"] == "buck"
    assert model.best(30.0, 48.0, 300.0, P)["mode"] == "boost"
    assert model.best(48.0, 48.0, 300.0, P)["mode"] == "buckboost"


def test_duties_match_ideal_ratio_plus_drops():
    r = model.evaluate(56.0, 48.0, 400.0, 100e3, "buck", P)
    assert r["d1"] > 48 / 56          # a little above ideal to cover resistive drops
    assert r["d1"] - 48 / 56 < 0.01
    r = model.evaluate(24.0, 48.0, 300.0, 100e3, "boost", P)
    assert r["d2"] == pytest.approx(0.5, abs=0.01)


def test_losses_physical_and_constraints():
    for vin in (12, 20, 24, 30, 40, 48, 52, 60):
        for frac in (0.1, 0.5, 1.0):
            r = model.best(float(vin), 48.0, frac * P.spec.p_rated(vin), P)
            assert r["feasible"], r["violations"]
            assert all(v >= 0 for v in r["losses"].values())
            assert 0.9 < r["eta"] < 1.0
            assert r["eta"] < r["eta_stage"]


def test_light_load_zvs():
    # at 10 % load the ripple exceeds twice the average current, the valley goes negative,
    # and every edge becomes soft-switched
    r = model.best(56.0, 48.0, 40.0, P)
    assert r["n_hard"] == 0
    r = model.best(56.0, 48.0, 400.0, P)
    assert r["n_hard"] > 0


def test_efficiency_honesty_bounds():
    # the model must not claim physics-defying numbers; low input voltage costs efficiency
    peak = max(model.best(float(v), 48.0, P.spec.p_rated(v) * f, P)["eta"] for v in (36, 48, 56) for f in (0.3, 0.5, 1.0))
    low = model.best(12.0, 48.0, P.spec.p_rated(12.0), P)["eta"]
    assert peak < 0.997
    assert low < peak - 0.01


def test_bypass():
    r = model.bypass(48.0, 400.0, P)
    assert r["eta"] > model.best(48.0, 48.0, 400.0, P)["eta"]


def test_power_derating():
    assert P.spec.p_rated(12.0) < 200
    assert P.spec.p_rated(48.0) == 400
