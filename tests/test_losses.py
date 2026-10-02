"""Worked examples for the loss equations (docs/EQUATIONS.md sections 3-5)."""
import pytest

from watt_forge import devices, efficiency, losses, magnetics, switched_cap as sc


def test_conduction_worked_example():
    # 10 A through 5 mOhm dissipates 0.5 W
    assert losses.conduction(10.0, 5e-3) == pytest.approx(0.5)
    # a 10 A switch at D=0.25 with 3 A ripple: Irms^2 = 0.25*(100 + 9/12) = 25.1875
    assert losses.rms_trapezoid(10.0, 3.0, 0.25) ** 2 == pytest.approx(25.1875)
    assert losses.rms_triangle_ac(3.0) == pytest.approx(3.0 / 12 ** 0.5)


def test_switching_worked_examples():
    # overlap: 1/2 * 48 V * 10 A * (10 ns + 10 ns) * 200 kHz = 0.96 W
    assert losses.overlap(48, 10, 10e-9, 10e-9, 200e3) == pytest.approx(0.96)
    # linear Coss: 1/2 * 1 nF * 48^2 * 200 kHz = 0.2304 W
    assert losses.coss_linear(1e-9, 48, 200e3) == pytest.approx(0.2304)
    # half-bridge hard turn-on with a linear 1 nF Coss: Q*V*f = C V^2 f = twice the single-device figure
    q = 1e-9 * 48
    assert losses.hard_turn_on_halfbridge(q, 48, 200e3) == pytest.approx(2 * 0.2304)
    # power-law Coss with m = 1 reduces to 1/2 C V^2
    assert losses.eoss_from_qoss(q, 48, 1.0) == pytest.approx(0.5 * 1e-9 * 48 ** 2)
    # gate: 28 nC * 5 V * 100 kHz = 14 mW (EPC2361)
    assert losses.gate_drive(28e-9, 5, 100e3) == pytest.approx(0.014)
    # dead time: 2 V * 10 A * 10 ns * 2 per period * 100 kHz = 40 mW
    assert losses.dead_time(2.0, 10.0, 10e-9, 100e3, 2) == pytest.approx(0.04)
    # reverse recovery (silicon ISC030N10NM6, 56 nC) at 48 V, 100 kHz = 0.2688 W; GaN = 0
    assert losses.reverse_recovery(56e-9, 48, 100e3) == pytest.approx(0.2688)
    assert losses.reverse_recovery(devices.get("EPC2361").qrr(), 48, 100e3) == 0.0


def test_zvs_residual():
    # 2 * 60 nC must move in the dead time: 12 A for 10 ns delivers exactly 120 nC -> full ZVS
    assert losses.zvs_residual_fraction(12.0, 10e-9, 60e-9) == pytest.approx(0.0)
    assert losses.zvs_residual_fraction(6.0, 10e-9, 60e-9) == pytest.approx(0.5)
    assert losses.zvs_residual_fraction(0.0, 10e-9, 60e-9) == pytest.approx(1.0)


def test_qoss_exponent_fit_reproduces_datasheet():
    # EPC2361: Co(er) = 1419 pF, Co(tr) = 1796 pF at 50 V. With Q = k V^m, E/(Q V) = m/(m+1).
    d = devices.get("EPC2361")
    e_ds = 0.5 * 1419e-12 * 50 ** 2
    q_ds = 1796e-12 * 50
    assert d.qoss(50) == pytest.approx(q_ds, rel=0.01)
    assert d.eoss(50) == pytest.approx(e_ds, rel=0.01)


def test_steinmetz_and_igse():
    mat = magnetics.MATERIALS["ferrite_generic"]
    k = magnetics.steinmetz_k(mat)
    # anchor: 300 kW/m^3 at 100 kHz, 100 mT
    assert magnetics.steinmetz(k, mat["alpha"], mat["beta"], 100e3, 0.1) == pytest.approx(300e3)
    # iGSE of a sinusoid must reproduce the Steinmetz equation
    import math
    n, f, bpk = 20000, 100e3, 0.05
    b = [bpk * math.sin(2 * math.pi * i / n) for i in range(n)]
    pv_igse = magnetics.igse_sampled(k, mat["alpha"], mat["beta"], b, 1 / f)
    assert pv_igse == pytest.approx(magnetics.steinmetz(k, mat["alpha"], mat["beta"], f, bpk), rel=2e-3)
    # triangular closed form equals the piecewise evaluation
    d, dbpp = 0.3, 0.04
    tri = magnetics.igse_triangular(k, mat["alpha"], mat["beta"], f, dbpp, d)
    pw = magnetics.igse_piecewise_linear(k, mat["alpha"], mat["beta"], [0, d / f, 1 / f], [0, dbpp, 0])
    assert tri == pytest.approx(pw, rel=1e-12)
    # at D = 0.5 a triangle loses a bit less than a sinusoid of the same peak-to-peak for alpha > 1
    assert magnetics.igse_triangular(k, mat["alpha"], mat["beta"], f, 0.1, 0.5) < magnetics.steinmetz(k, mat["alpha"], mat["beta"], f, 0.05) * 1.05


def test_switched_capacitor_limits():
    c, r = 10e-6, 10e-3
    # worked example: 48 V into a 23.5 V battery through 10 uF at 100 kHz (slow limit):
    # R_SSL = 1/(4 C f) = 0.25 ohm, so (24 - 23.5)/0.25 = 2 A and the loss is 2^2 * 0.25 = 1.0 W
    res = sc.simulate_series_parallel(48, 23.5, c, r, 100e3)
    assert sc.r_ssl([0.5], [c], 100e3) == pytest.approx(0.25)
    assert res["r_out"] == pytest.approx(0.25, rel=1e-3)
    assert res["i_out"] == pytest.approx(2.0, rel=1e-3)
    assert res["p_loss"] == pytest.approx(1.0, rel=1e-3)
    # fast limit: R_FSL = 2 * 4 * r * (1/2)^2 = 2 r
    fast = sc.simulate_series_parallel(48, 23.5, c, r, 1e8)
    assert fast["r_out"] == pytest.approx(2 * r, rel=0.01)
    # the smooth approximation is within 10 % everywhere in between
    for f in (1e4, 1e5, 3e5, 1e6, 3e6):
        exact = sc.simulate_series_parallel(48, 23.5, c, r, f)["r_out"]
        assert sc.r_out([0.5], [c], f, [0.5] * 4, [r] * 4) == pytest.approx(exact, rel=0.10)
    # brute-force Euler integration agrees with the closed-form steady state
    num = sc.simulate_series_parallel_numeric(48, 23.5, c, r, 100e3, steps_per_phase=2000, periods=40)
    assert num["r_out"] == pytest.approx(res["r_out"], rel=1e-3)
    # efficiency of an SC stage: Vout/(n Vin)
    assert sc.sc_efficiency(48, 0.5, 2.0, 0.25) == pytest.approx(23.5 / 24)


def test_efficiency_and_weighting():
    assert efficiency.efficiency(400, {"a": 2.0, "b": 2.0}) == pytest.approx(400 / 404)
    assert sum(efficiency.CEC_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(efficiency.EURO_WEIGHTS.values()) == pytest.approx(1.0)
    assert efficiency.cec(lambda f: 0.98) == pytest.approx(0.98)
    # worked example: light-load droop pulls the weighted number below the 75 % point
    table = {0.05: 0.95, 0.10: 0.97, 0.20: 0.98, 0.30: 0.985, 0.50: 0.99, 0.75: 0.99, 1.00: 0.985}
    assert efficiency.cec(table.get) == pytest.approx(0.04 * 0.97 + 0.05 * 0.98 + 0.12 * 0.985 + 0.21 * 0.99 + 0.53 * 0.99 + 0.05 * 0.985)
    assert efficiency.euro(table.get) == pytest.approx(0.03 * 0.95 + 0.06 * 0.97 + 0.13 * 0.98 + 0.10 * 0.985 + 0.48 * 0.99 + 0.20 * 0.985)
