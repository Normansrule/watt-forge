"""README/site charts for the control library, from data/control_traces.json and
data/control_efficiency.json (run scripts/make_control_data.py first).

    python scripts/make_control_charts.py
Writes docs/img/mppt_shading.png, docs/img/mppt_clouds.png and docs/img/efficiency_controls.png.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from watt_forge.control import efficiency as E  # noqa: E402
from watt_forge.style import LIGHT, apply_mpl  # noqa: E402

IMG = ROOT / "docs" / "img"
NAMES = {"po": "P&O (fixed step)", "vspo": "P&O (variable step)", "inc": "InC (fixed step)", "vsinc": "InC (variable step)",
         "focv": "Fractional Voc", "esc": "Extremum seeking", "pso": "Particle swarm", "scan": "Global scan"}


def race(profile: str, keys, title: str, out: Path, xlim=None):
    tr = json.loads((ROOT / "data" / "control_traces.json").read_text())[profile]
    bench = json.loads((ROOT / "data" / "control_benchmark.json").read_text())["results"][profile]
    apply_mpl(LIGHT)
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    t = tr["t"]
    ax.plot(t, tr["pmpp"], color=LIGHT["text"], lw=1.3, ls=(0, (4, 3)), label="available (global MPP)")
    for n, k in enumerate(keys):
        ax.plot(t, tr[k]["p"], color=LIGHT["series"][n], lw=1.6,
                label=f"{NAMES[k]}: {100 * bench[k]['eta_mppt']:.2f} %")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("panel power (W)")
    ax.set_ylim(0, max(tr["pmpp"]) * 1.12)
    if xlim:
        ax.set_xlim(*xlim)
    ax.set_title(title)
    ax.legend(loc="lower center", ncol=3, fontsize=8, bbox_to_anchor=(0.5, -0.42))
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def efficiency_curves(out: Path, vin=36.0, pout=60.0):
    apply_mpl(LIGHT)
    op = E.operating_point(vin, 48.0, pout, kappa=E.kappa_estimate(vin, pout))
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.3), dpi=150)
    fc = [c for c in E.fs_curve(vin, 48.0, pout) if c["loss"] is not None]
    a.plot([c["fs"] / 1e3 for c in fc], [c["loss"] for c in fc], color=LIGHT["series"][0])
    a.scatter([op["fs"]["fixed"] / 1e3], [op["loss"]["base"]], color=LIGHT["series"][3], zorder=3, label="fixed 100 kHz")
    fs_loss = {c["fs"]: c["loss"] for c in fc}
    a.scatter([op["fs"]["online"] / 1e3], [fs_loss[op["fs"]["online"]]], color=LIGHT["series"][2], zorder=3,
              label=f"online hill climb (lands here {100 * op['fs']['hit_rate']:.0f} % of trials)" if op["fs"]["online"] == op["fs"]["optimum"]
              else "online hill climb (most common landing)")
    a.set_xlabel("switching frequency (kHz)")
    a.set_ylabel("converter loss (W)")
    a.set_title(f"Adaptive frequency ({vin:.0f} V, {pout:.0f} W)")
    a.legend(fontsize=8)
    tc = [c for c in E.td_curve(vin, 48.0, pout, op["fs"]["online"]) if c["loss"] is not None]
    b.plot([c["td"] * 1e9 for c in tc], [c["loss"] for c in tc], color=LIGHT["series"][2])
    td_loss = {round(c["td"] * 1e9): c["loss"] for c in tc}
    b.scatter([op["td"]["fixed"] * 1e9], [op["td"]["loss_fixed"]], color=LIGHT["series"][3], zorder=3, label="fixed design value")
    b.scatter([op["td"]["online"] * 1e9], [td_loss[round(op["td"]["online"] * 1e9)]], color=LIGHT["series"][2], zorder=3,
              label="online hill climb (most common landing)")
    b.set_xlabel("dead time (ns)")
    b.set_title("Adaptive dead time: stops where gains fall below resolution")
    b.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


if __name__ == "__main__":
    race("shading", ["po", "vsinc", "esc", "pso", "scan"],
         "Partial shading: only global search finds the true peak",
         IMG / "mppt_shading.png")
    race("clouds", ["po", "vspo", "vsinc", "esc", "scan"],
         "Cloud edges: how fast each tracker recovers", IMG / "mppt_clouds.png")
    efficiency_curves(IMG / "efficiency_controls.png")
    print("control charts written")
