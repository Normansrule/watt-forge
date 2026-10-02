"""HDL modulator self-checking testbench, PV model, and the netlist guard."""
import shutil
import subprocess
from pathlib import Path

import pytest

from watt_forge import pv, spice

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hardware" / "flagship" / "hdl"


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_pwm_modulator_testbench(tmp_path):
    exe = tmp_path / "tb"
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), str(HDL / "wf_pwm3l.v"), str(HDL / "tb_wf_pwm3l.v")],
                   check=True, capture_output=True)
    out = subprocess.run(["vvp", "-n", str(exe)], capture_output=True, text=True, timeout=600).stdout
    assert "PASS" in out, out[-2000:]


def test_panel_stc_and_shading():
    p = pv.Panel()
    assert pv.panel_voltage(0.0, [1000] * 3, 25, p) == pytest.approx(49.5, abs=0.05)
    assert pv.panel_current(0.0, [1000] * 3, 25, p) == pytest.approx(10.4, abs=0.02)
    mpp = pv.global_mpp([1000] * 3, 25, p)
    assert 370 < mpp["p"] < 400 and 37 < mpp["v"] < 42
    # hot panel: lower voltage and power
    assert pv.global_mpp([1000] * 3, 60, p)["p"] < mpp["p"]
    # shading one substring creates a second local maximum
    curve = pv.pv_curve([1000, 1000, 250], 25, p, n=300)
    ps = [c["p"] for c in curve]
    peaks = [i for i in range(1, len(ps) - 1) if ps[i] > ps[i - 1] and ps[i] >= ps[i + 1]]
    assert len(peaks) >= 2


GOOD = """* good
V1 in 0 DC 12
R1 in out 1k
C1 out 0 1u
.tran 1u 1m
.meas tran vavg AVG v(out)
.end
"""


def test_guard_accepts_plain_netlist():
    assert spice.check_netlist(GOOD) == []


@pytest.mark.parametrize("bad", [
    GOOD.replace(".end", ".control\nshell rm -rf ~\n.endc\n.end"),
    GOOD.replace(".end", ".include /etc/passwd\n.end"),
    GOOD.replace(".end", ".lib /tmp/x.lib tt\n.end"),
    GOOD.replace(".tran 1u 1m", ".tran 1p 10"),
    GOOD.replace("R1 in out 1k", "Z1 in out 1k"),
    GOOD.replace(".end", ".exec shell ls\n.end"),
    GOOD.replace(".end", ".option\n+ shell=1\n.end"),
    "*x\n" + "R1 a b 1\n" * 30000,
])
def test_guard_rejects_malicious(bad):
    with pytest.raises(spice.NetlistRejected):
        spice.check_netlist(bad)


@pytest.mark.skipif(not spice.ngspice_available(), reason="ngspice not installed")
def test_sandboxed_run():
    out = spice.run(GOOD, timeout_s=30)
    assert out["vavg"] == pytest.approx(12.0, rel=0.01)


def _guard_cases():
    text = (Path(__file__).parent / "fixtures" / "guard_cases.txt").read_text()
    cases, cur = [], None
    for line in text.splitlines(keepends=True):
        if line.startswith("==="):
            _, verdict, name = line.split(maxsplit=2)
            cur = [name.strip(), verdict == "ok", ""]
            cases.append(cur)
        elif cur is not None:
            cur[2] += line
    return cases


@pytest.mark.parametrize("name,ok,net", _guard_cases(), ids=[c[0] for c in _guard_cases()])
def test_guard_shared_cases(name, ok, net):
    if ok:
        assert spice.check_netlist(net) == []
    else:
        with pytest.raises(spice.NetlistRejected):
            spice.check_netlist(net)


def test_spice_presets_pass_guard_and_match_model():
    import json
    doc = json.loads((Path(__file__).resolve().parents[1] / "data" / "spice_presets.json").read_text())
    assert len(doc["presets"]) >= 5
    for p in doc["presets"]:
        assert spice.check_netlist(p["netlist"]) == []
        r, e = p["result"], p["expect"]
        if "conduction_only_eta" in e:
            assert r["eta"] == pytest.approx(e["conduction_only_eta"], abs=5e-5)
            assert r["eta"] > e["full_model_eta"]  # conduction-only must beat the full model
        for k in ("vavg", "vout"):
            if k in e:
                assert r[k] == pytest.approx(e[k], rel=2e-3)
