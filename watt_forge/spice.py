"""ngspice integration: netlist generation for cross-checks, a guard for untrusted
netlists, and a sandboxed batch runner (no .control blocks, no includes, time-limited).

The desktop app uses the same rules (desktop/netlist-guard is the Rust port).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

# ------------------------------------------------------------------ guard

MAX_BYTES = 256 * 1024
MAX_LINES = 20000
MAX_TRAN_POINTS = 5_000_000
ALLOWED_ELEMENTS = set("RCLVISDEGFHBKXMQJ")
ALLOWED_DOT = {".model", ".tran", ".ic", ".param", ".meas", ".measure", ".option", ".options",
               ".end", ".title", ".subckt", ".ends", ".global", ".temp", ".op", ".dc", ".ac",
               ".save", ".func", ".nodeset"}
FORBIDDEN_TOKENS = re.compile(r"\b(shell|system|exec|wrdata|write|wrs2p|load|source|cd|setcs|codemodel|pre_osdi|osdi)\b", re.I)
_SUFFIX = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}


class NetlistRejected(ValueError):
    pass


def parse_spice_number(tok: str) -> float:
    m = re.fullmatch(r"([+-]?\d*\.?\d+(?:e[+-]?\d+)?)(meg|[tgkmunpf])?[a-z]*", tok.strip().lower())
    if not m:
        raise NetlistRejected(f"not a number: {tok!r}")
    return float(m.group(1)) * _SUFFIX.get(m.group(2) or "", 1.0)


def check_netlist(text: str) -> List[str]:
    """Validate an untrusted netlist. Returns warnings; raises NetlistRejected on any violation."""
    warnings: List[str] = []
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        raise NetlistRejected("netlist too large")
    if "\x00" in text:
        raise NetlistRejected("binary content")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise NetlistRejected("too many lines")
    for n, raw in enumerate(lines[1:], start=2):  # first line is the title in SPICE
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith(";"):
            continue
        if line.startswith("+"):
            body = line[1:]
        else:
            body = line
        low = body.lower()
        if FORBIDDEN_TOKENS.search(low):
            raise NetlistRejected(f"line {n}: forbidden command")
        if low.startswith("."):
            word = low.split()[0]
            if word in (".control", ".endc", ".include", ".inc", ".lib", ".endl", ".exec", ".csparam"):
                raise NetlistRejected(f"line {n}: {word} is not allowed")
            if word not in ALLOWED_DOT:
                raise NetlistRejected(f"line {n}: unknown dot command {word}")
            if word == ".tran":
                toks = low.split()
                try:
                    tstep, tstop = parse_spice_number(toks[1]), parse_spice_number(toks[2])
                except (IndexError, NetlistRejected):
                    raise NetlistRejected(f"line {n}: malformed .tran")
                if tstep <= 0 or tstop / tstep > MAX_TRAN_POINTS:
                    raise NetlistRejected(f"line {n}: .tran asks for too many points")
            continue
        if line.startswith("+"):
            continue
        if body[0].upper() not in ALLOWED_ELEMENTS:
            raise NetlistRejected(f"line {n}: element type {body[0]!r} not allowed")
    if not any(l.strip().lower() == ".end" for l in lines):
        warnings.append("no .end card (added automatically)")
    return warnings


def ngspice_available() -> bool:
    return shutil.which("ngspice") is not None


def run(netlist: str, timeout_s: float = 60.0, trusted: bool = False) -> Dict[str, float]:
    """Run ngspice in batch mode in a throwaway directory; parse .meas results."""
    if not trusted:
        check_netlist(netlist)
    if not ngspice_available():
        raise RuntimeError("ngspice not installed")
    with tempfile.TemporaryDirectory(prefix="wattforge-") as d:
        path = os.path.join(d, "circuit.cir")
        with open(path, "w") as f:
            f.write(netlist if netlist.rstrip().lower().endswith(".end") else netlist + "\n.end\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": d, "SPICE_NO_DATASEG_CHECK": "1"}
        cp = subprocess.run(["ngspice", "-b", path], cwd=d, env=env, capture_output=True, text=True, timeout=timeout_s)
    out: Dict[str, float] = {}
    for line in (cp.stdout + "\n" + cp.stderr).splitlines():
        m = re.match(r"\s*([a-z_][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)", line)
        if m:
            try:
                out[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
    out["_returncode"] = cp.returncode
    return out


# ------------------------------------------------------------- generators

def _pulse(name: str, node: str, start: float, width: float, T: float, rise: float = 1e-10) -> str:
    """Gate source high during [start, start+width) mod T (level 1 V)."""
    start %= T
    if width >= T - 1e-15:
        return f"{name} {node} 0 DC 1"
    if width <= 0:
        return f"{name} {node} 0 DC 0"
    return f"{name} {node} 0 PULSE(0 1 {start:.9e} {rise:.3e} {rise:.3e} {max(width - rise, rise):.9e} {T:.9e})"


def _wrap_on(name, node, start, width, T):
    """Gate source high during [start, start+width) mod T, written so the value at t=0 is
    already correct (with 'uic' there is no operating point to settle a 0 V gate)."""
    start %= T
    if width >= T - 1e-15:
        return [f"{name} {node} 0 DC 1"]
    if width <= 0:
        return [f"{name} {node} 0 DC 0"]
    on_at_zero = start < 1e-15 * T or start + width > T + 1e-15
    if not on_at_zero:
        return [_pulse(name, node, start, width, T)]
    # high at t=0: describe the LOW window instead with PULSE(1 0 ...)
    low_start = (start + width) % T
    low_w = T - width
    return [f"{name} {node} 0 PULSE(1 0 {low_start:.9e} 1e-10 1e-10 {max(low_w - 1e-10, 1e-10):.9e} {T:.9e})"]


def flagship_netlist(vin, vout, mode, d1, d2, phase, fs, r_sw, r_loop_extra, l, c1, c2, esr, x0, periods=40, meas_periods=10):
    """Conduction-only three-level buck-boost netlist (zero dead time, ideal switches with Ron)."""
    T = 1.0 / fs
    in_active = mode in ("buck", "buckboost")
    out_active = mode in ("boost", "buckboost")
    i0 = x0[0]
    v1 = x0[1] if in_active else vin / 2
    v2 = x0[-1] if out_active else vout / 2
    n = [f"* watt-forge flagship cross-check {mode} Vin={vin} Vout={vout} fs={fs}"]
    n.append(f".model SWM SW(VT=0.5 VH=0 RON={r_sw:.6e} ROFF=1e8)")
    n.append(f"VIN in 0 DC {vin}")
    n.append(f"VOUT out 0 DC {vout}")
    # input leg
    n += ["S1 in t1 g1 0 SWM", "S2 t1 A g2 0 SWM", "S3 A b1 g3 0 SWM", "S4 b1 0 g4 0 SWM",
          f"RCF1 t1 cf1 {esr:.6e}", f"CF1 cf1 b1 {c1:.6e} IC={v1:.9e}"]
    if in_active:
        n += _wrap_on("VG1", "g1", 0.0, d1 * T, T)
        n += _wrap_on("VG2", "g2", T / 2, d1 * T, T)
        n += _wrap_on("VG4", "g4", d1 * T, (1 - d1) * T, T)
        n += _wrap_on("VG3", "g3", T / 2 + d1 * T, (1 - d1) * T, T)
    else:
        n += ["VG1 g1 0 DC 1", "VG2 g2 0 DC 1", "VG3 g3 0 DC 0", "VG4 g4 0 DC 0"]
    n.append(f"L1 A lx {l:.6e} IC={i0:.9e}")
    n.append(f"RL lx B {r_loop_extra:.6e}")
    n += ["S6 B t2 g6 0 SWM", "S5 t2 out g5 0 SWM", "S7 B b2 g7 0 SWM", "S8 b2 0 g8 0 SWM",
          f"RCF2 t2 cf2 {esr:.6e}", f"CF2 cf2 b2 {c2:.6e} IC={v2:.9e}"]
    if out_active:
        n += _wrap_on("VG8", "g8", phase * T, d2 * T, T)
        n += _wrap_on("VG7", "g7", phase * T + T / 2, d2 * T, T)
        n += _wrap_on("VG5", "g5", phase * T + d2 * T, (1 - d2) * T, T)
        n += _wrap_on("VG6", "g6", phase * T + T / 2 + d2 * T, (1 - d2) * T, T)
    else:
        n += ["VG5 g5 0 DC 1", "VG6 g6 0 DC 1", "VG7 g7 0 DC 0", "VG8 g8 0 DC 0"]
    t_end = periods * T
    t_start = (periods - meas_periods) * T
    n.append(f".tran {T/2000:.6e} {t_end:.6e} 0 {T/4000:.6e} uic")
    n.append(f".meas tran pin AVG par('-v(in)*i(VIN)') FROM={t_start:.9e} TO={t_end:.9e}")
    n.append(f".meas tran pout AVG par('v(out)*i(VOUT)') FROM={t_start:.9e} TO={t_end:.9e}")
    n.append(f".meas tran ilavg AVG i(L1) FROM={t_start:.9e} TO={t_end:.9e}")
    n.append(".end")
    return "\n".join(n) + "\n"


def buck_netlist(vin, d, fs, l, c, r_load, r_on, r_l, periods=400, meas_periods=20):
    """Synchronous buck feeding a resistor, for the textbook ratio-with-losses check."""
    T = 1.0 / fs
    n = [f"* watt-forge sync buck worked example",
         f".model SWM SW(VT=0.5 VH=0 RON={r_on:.6e} ROFF=1e8)",
         f"VIN in 0 DC {vin}",
         "SH in sw gh 0 SWM", "SL sw 0 gl 0 SWM",
         _pulse("VGH", "gh", 0.0, d * T, T), _pulse("VGL", "gl", d * T, (1 - d) * T, T),
         f"L1 sw lx {l:.6e}", f"RL lx out {r_l:.6e}", f"C1 out 0 {c:.6e}", f"RLOAD out 0 {r_load:.6e}",
         f".tran {T/400:.6e} {periods*T:.6e} 0 {T/800:.6e}",
         f".meas tran vout AVG v(out) FROM={(periods-meas_periods)*T:.9e} TO={periods*T:.9e}",
         ".end"]
    return "\n".join(n) + "\n"
