"""The time-domain circuit simulation must reproduce the analytic efficiency curve,
conserve energy, and agree with ngspice."""
import pytest

from watt_forge import spice
from watt_forge.flagship import model, sim
from watt_forge.flagship.params import Params

P = Params()
GRID = [(12.0, 1.0), (18.0, 0.5), (24.0, 1.0), (30.0, 0.3), (36.0, 0.75), (46.0, 1.0),
        (48.0, 1.0), (50.0, 0.5), (56.0, 1.0), (60.0, 0.1)]


@pytest.mark.parametrize("vin,frac", GRID)
def test_sim_reproduces_model(vin, frac):
    pout = frac * P.spec.p_rated(vin)
    a = model.best(vin, 48.0, pout, P)
    s = sim.simulate(vin, 48.0, pout, a["fs"], a["mode"], P, a["phase"])
    assert s["pout"] == pytest.approx(pout, rel=1e-6)
    # efficiency agreement: 0.15 percentage points
    assert abs(s["eta"] - a["eta"]) < 0.0015, (s["eta"], a["eta"])
    # energy conservation inside the circuit solve
    assert abs(s["energy_residual"]) < 1e-3 * pout
    # periodic steady state closes
    assert s["closure"] < 1e-6


def test_flying_caps_self_balance():
    a = model.best(56.0, 48.0, 400.0, P)
    s = sim.simulate(56.0, 48.0, 400.0, a["fs"], a["mode"], P, a["phase"])
    v1 = s["x0"][1]
    assert v1 == pytest.approx(28.0, rel=0.02)


@pytest.mark.skipif(not spice.ngspice_available(), reason="ngspice not installed")
@pytest.mark.parametrize("vin,frac", [(56.0, 1.0), (24.0, 1.0), (48.0, 1.0), (36.0, 0.5)])
def test_circuit_matches_ngspice(vin, frac):
    pout = frac * P.spec.p_rated(vin)
    a = model.best(vin, 48.0, pout, P)
    s = sim.ideal_switch_efficiency(vin, 48.0, pout, a["fs"], a["mode"], P, a["phase"])
    ckt = s["res"]["ckt"]
    net = spice.flagship_netlist(vin, 48.0, a["mode"], s["d1"], s["d2"], s["phase"], a["fs"], ckt.r_sw,
                                 ckt.dcr + P.r_pcb, P.l, ckt.c1, ckt.c2, ckt.esr, s["x0"])
    out = spice.run(net, timeout_s=300, trusted=True)
    assert out["_returncode"] == 0
    assert out["pout"] / out["pin"] == pytest.approx(s["eta"], abs=5e-5)
    assert out["pout"] == pytest.approx(s["pout"], rel=2e-3)
