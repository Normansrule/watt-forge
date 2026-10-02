"""Reference controller: C == Python in closed loop, and the MPPT behaves."""
import shutil
import subprocess
from pathlib import Path

import pytest

from watt_forge import pv
from watt_forge.flagship import control as C

ROOT = Path(__file__).resolve().parents[1]
CDIR = ROOT / "hardware" / "flagship" / "control"
PANEL = pv.Panel()


def _plant_meas(out, env):
    if out.state in (C.S_TRACK, C.S_SWEEP, C.S_BYPASS) and out.mode != C.M_OFF:
        vin = out.vin_ref
        iin = pv.panel_current(vin, env["g"], env["t"], PANEL)
    else:
        vin, iin = pv.panel_voltage(0.0, env["g"], env["t"], PANEL), 0.0
    return C.Meas(vin=vin, iin=iin, vout=env["vout"], temp=env.get("temp", 40.0))


def _profile():
    prof = []
    for k in range(6200):
        g = 1000.0 if k < 3000 else 650.0
        gs = [g, g, g]
        if 4200 <= k < 5200:
            gs = [g, g, 250.0]                      # partial shading: two local maxima
        vout = 48.0 + (9.9 if k >= 5700 else 0.0)   # battery reaches the constant-voltage limit
        prof.append({"g": gs, "t": 40.0, "vout": vout})
    return prof


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not installed")
    exe = tmp_path_factory.mktemp("c") / "wf_harness"
    subprocess.run(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(exe),
                    str(CDIR / "wf_ctrl.c"), str(CDIR / "wf_harness.c"), "-lm"], check=True)
    return exe


def test_c_matches_python_closed_loop(harness):
    ctrl = C.Ctrl()
    proc = subprocess.Popen([str(harness)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    out = C.Out()
    mismatches = []
    for k, env in enumerate(_profile()):
        m = _plant_meas(out, env)
        proc.stdin.write(f"{m.vin!r} {m.iin!r} {m.vout!r} {m.iout!r} {m.temp!r}\n")
        line_c = proc.stdout.readline().strip()
        out = ctrl.step_once(m)
        if line_c != out.line():
            mismatches.append((k, line_c, out.line()))
    proc.stdin.close()
    proc.wait()
    assert not mismatches, mismatches[:3]


def _run(profile):
    ctrl = C.Ctrl()
    out = C.Out()
    trace = []
    for env in profile:
        m = _plant_meas(out, env)
        out = ctrl.step_once(m)
        trace.append((m, out))
    return trace


def test_mppt_tracking_efficiency():
    prof = _profile()
    trace = _run(prof[:3000])
    mpp = pv.global_mpp([1000.0] * 3, 40.0, PANEL)["p"]
    tail = [m.vin * m.iin for m, o in trace[2000:3000]]
    assert sum(tail) / len(tail) > 0.995 * mpp


def test_partial_shading_finds_global_maximum():
    prof = _profile()
    trace = _run(prof[:5200])
    mpp = pv.global_mpp([650.0, 650.0, 250.0], 40.0, PANEL)
    tail = [(m.vin, m.vin * m.iin) for m, o in trace[4800:5200]]
    assert sum(p for _, p in tail) / len(tail) > 0.99 * mpp["p"]
    # it is on the low-voltage (two-substring) hill, not the local maximum near 38 V
    assert abs(sum(v for v, _ in tail) / len(tail) - mpp["v"]) < 2.0


def test_constant_voltage_limit_backs_off():
    trace = _run(_profile())
    ps = [m.vin * m.iin for m, o in trace]
    assert ps[-1] < 0.5 * max(ps[5500:5700])   # power folded back while Vout > VOUT_CV
    assert all(o.state != C.S_FAULT for _, o in trace)


def test_bypass_when_mpp_matches_battery():
    # 25 C STC panel has its MPP near 39.9 V; with a 40 V battery the controller should bypass
    prof = [{"g": [1000.0] * 3, "t": 25.0, "vout": 40.0}] * 3000
    trace = _run(prof)
    assert any(o.state == C.S_BYPASS for _, o in trace)
    bp = [o for _, o in trace if o.state == C.S_BYPASS]
    assert all(o.mode == C.M_BYPASS and o.fs == 0.0 for o in bp)


def test_fault_latch_and_retry():
    ok = {"g": [1000.0] * 3, "t": 25.0, "vout": 48.0}
    bad = dict(ok, vout=60.5)                     # battery over-voltage
    trace = _run([ok] * 1500 + [bad] * 10 + [ok] * 7000)
    states = [o.state for _, o in trace]
    assert C.S_FAULT in states[1500:1512]
    first_ok = next(i for i in range(1510, len(states)) if states[i] != C.S_FAULT)
    assert first_ok - 1510 >= C.FAULT_RETRY_TICKS - 1
    assert states[-1] == C.S_TRACK
