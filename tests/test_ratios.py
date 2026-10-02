"""Worked examples for conversion ratios and balance laws (docs/EQUATIONS.md sections 1-2)."""
import math

import pytest

from watt_forge import ratios, spice


def test_ideal_ratios_worked_examples():
    # 48 V -> 12 V buck needs D = 0.25
    assert ratios.duty_for_ratio("buck", 12 / 48) == pytest.approx(0.25)
    # 24 V -> 48 V boost needs D = 0.5
    assert ratios.duty_for_ratio("boost", 2.0) == pytest.approx(0.5)
    assert ratios.m_boost(0.5) == pytest.approx(2.0)
    # inverting buck-boost at D = 1/3 gives M = -0.5
    assert ratios.m_buck_boost(1 / 3) == pytest.approx(-0.5)
    assert ratios.m_sepic(0.6) == pytest.approx(1.5)
    assert ratios.m_cuk(0.6) == pytest.approx(-1.5)
    assert ratios.m_flyback(0.4, 0.5) == pytest.approx(0.5 * 0.4 / 0.6)
    assert ratios.m_four_switch(0.9, 0.25) == pytest.approx(1.2)
    for top in ("buck", "boost", "buck_boost", "sepic", "cuk"):
        for m in (0.3, 0.9, 1.7, 3.0):
            if top == "buck" and m >= 1:
                continue
            if top == "boost" and m <= 1:
                continue
            d = ratios.duty_for_ratio(top, m)
            assert abs(ratios.IDEAL_RATIO[top](d)) == pytest.approx(m)


def test_lossy_ratio_worked_example():
    # Boost, D = 0.5, R = 10 ohm, r_on = 20 mOhm, r_L = 30 mOhm:
    # M = 2 / (1 + 0.05 / (0.25 * 10)) = 2 / 1.02 = 1.96078...
    assert ratios.m_boost_lossy(0.5, 10, 0.02, 0.03) == pytest.approx(2 / 1.02)
    # buck: M = D / (1 + (r_on + r_l)/R)
    assert ratios.m_buck_lossy(0.25, 1.44, 0.004, 0.006) == pytest.approx(0.25 / (1 + 0.01 / 1.44))
    # losses always pull the ratio below ideal
    assert ratios.m_buck_boost_lossy(0.6, 5, 0.01, 0.01) < abs(ratios.m_buck_boost(0.6))


def test_volt_second_and_charge_balance():
    # Ideal buck 48 -> 12 V at D = 0.25: vL = +36 V for 0.25 T, -12 V for 0.75 T
    assert ratios.volt_second_residual([36.0, -12.0], [0.25, 0.75]) == pytest.approx(0.0)
    # wrong duty leaves a net volt-second, so the current would ratchet
    assert ratios.volt_second_residual([36.0, -12.0], [0.3, 0.7]) > 0
    # Boost output capacitor: -Iout for D T, (IL - Iout) for (1-D) T; IL = Iout/(1-D)
    iout, d = 2.0, 0.5
    il = iout / (1 - d)
    assert ratios.charge_residual([-iout, il - iout], [d, 1 - d]) == pytest.approx(0.0)


def test_ccm_dcm_boundary_is_continuous():
    # At K = K_crit the DCM ratio must equal the CCM ratio.
    for top, mccm in (("buck", ratios.m_buck), ("boost", ratios.m_boost), ("buck_boost", ratios.m_buck_boost)):
        for d in (0.2, 0.4, 0.6):
            kc = ratios.k_crit(top, d)
            r, fs = 10.0, 100e3
            l = kc * r / (2 * fs)
            assert ratios.m_dcm(top, d, l, r, fs) == pytest.approx(mccm(d), rel=1e-9)


def test_sizing_worked_example():
    # Buck 48 -> 12 V, 10 A, 200 kHz, 30 % ripple (3 A pk-pk): L = (48-12)*0.25/(3*200e3) = 15 uH
    l = ratios.inductor_for_ripple("buck", 48, 12, 0.25, 3.0, 200e3)
    assert l == pytest.approx(15e-6)
    assert ratios.ripple_current("buck", 48, 12, 0.25, l, 200e3) == pytest.approx(3.0)
    # 1 % (120 mV) output ripple: C = dI/(8 fs dV) = 3/(8*200e3*0.12) = 15.625 uF
    assert ratios.output_cap_for_ripple("buck", 10, 0.25, 3.0, 0.12, 200e3) == pytest.approx(15.625e-6)


@pytest.mark.skipif(not spice.ngspice_available(), reason="ngspice not installed")
def test_lossy_buck_ratio_against_ngspice():
    vin, d, fs = 48.0, 0.25, 200e3
    r_load, r_on, r_l = 1.44, 0.01, 0.02
    net = spice.buck_netlist(vin, d, fs, 15e-6, 200e-6, r_load, r_on, r_l, periods=1500, meas_periods=50)
    out = spice.run(net, timeout_s=120, trusted=True)
    expect = vin * ratios.m_buck_lossy(d, r_load, r_on, r_l)
    assert out["vout"] == pytest.approx(expect, rel=2e-3)
