"""Generate the README / site charts and the hero GIF from data/flagship_results.json.

Run after `python -m watt_forge.flagship.design`:
    python scripts/make_charts.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from watt_forge import switched_cap as sc  # noqa: E402
from watt_forge.style import LIGHT, apply_mpl, group_losses, LOSS_GROUPS  # noqa: E402

IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
R = json.loads((ROOT / "data" / "flagship_results.json").read_text())
T = LIGHT
S = T["series"]
apply_mpl(T)


def _save(fig, name):
    fig.savefig(IMG / f"{name}.png", dpi=150, bbox_inches="tight")
    fig.savefig(IMG / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def mode_bands(ax, vins, pts, y0, y1):
    """Grey text bands naming the operating mode along the Vin axis."""
    spans = []
    for v, p in zip(vins, pts):
        lab = p["label"].replace(" (SC 1:2 region)", " SC 1:2")
        if spans and spans[-1][2] == lab:
            spans[-1][1] = v
        else:
            spans.append([v, v, lab])
    for a, b, lab in spans:
        ax.axvspan(a - 0.5, b + 0.5, color=T["grid"], alpha=0.35 if "SC" in lab or "buckboost" in lab else 0.0, lw=0)
        ax.text((a + b) / 2, y1, lab.replace("buckboost", "buck-\nboost"), ha="center", va="top", fontsize=8, color=T["muted"])


def eff_vs_vin():
    vins = R["vins"]
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    keys = [("0.1", "10 % load"), ("0.3", "30 %"), ("0.5", "50 %"), ("1.0", "100 % (rated)")]
    for (k, lab), col in zip(keys, S):
        eta = [100 * p["eta"] for p in R["curves"][k]]
        ax.plot(vins, eta, color=col, label=lab)
        ax.plot(vins[-1], eta[-1], "o", color=col, ms=6, mec=T["surface"], mew=2)
    ax.set_xlabel("Panel (input) voltage [V]  -  output fixed at 48 V")
    ax.set_ylabel("Predicted efficiency [%]")
    ax.set_ylim(94.5, 100)
    mode_bands(ax, vins, R["curves"]["1.0"], 94.5, 99.97)
    ax.set_title("Flagship: predicted efficiency vs input voltage (model, includes 0.55 W housekeeping)")
    ax.legend(loc="lower right", ncols=2, fontsize=8)
    fig.text(0.01, -0.03, "Model prediction, not a measurement. Unmodelled layout, thermal and measurement effects can cost "
             "several tenths of a point;\nthe dip at 48 V is the both-legs-switching buck-boost mode (bypass avoids it).",
             fontsize=7.5, color=T["text2"])
    _save(fig, "eff_vs_vin")


def donut(ax, losses, title, total_label):
    groups = [(n, v) for n, v in group_losses(losses)]
    vals = [v for _, v in groups]
    wedges, _ = ax.pie(vals, colors=S[:6], startangle=90, counterclock=False,
                       wedgeprops={"width": 0.36, "edgecolor": T["surface"], "linewidth": 2})
    ax.text(0, 0.06, f"{sum(vals):.2f} W", ha="center", va="center", fontsize=14, weight="semibold", color=T["text"])
    ax.text(0, -0.16, total_label, ha="center", va="center", fontsize=8, color=T["text2"])
    ax.set_title(title, fontsize=10, loc="center")
    return wedges


def loss_budget():
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.9))
    pts = [("buck_56V_400W", "56 V -> 48 V, 400 W (buck)"), ("sc_24V_300W", "24 V -> 48 V, 300 W (SC 1:2)"),
           ("boost_12V_rated", "12 V -> 48 V, 175 W (boost)")]
    for ax, (k, title) in zip(axes, pts):
        p = R["nominal"][k]
        w = donut(ax, p["losses"], title, f"total loss, eta {100*p['eta']:.2f} %")
    fig.legend(w, [n for n, _ in LOSS_GROUPS], loc="lower center", ncols=6, fontsize=8, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Where the watts go: flagship loss budget at three operating points", x=0.02, ha="left", weight="semibold")
    _save(fig, "loss_budget")


def device_compare():
    tc = R["tech_compare"]
    names = list(tc.keys())
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    y = list(range(len(names)))[::-1]
    for yi, n in zip(y, names):
        row = [r for r in tc[n]["rows"] if r["vin"] == 36.0][0]
        left = 0.0
        for (gname, gval), col in zip(group_losses(row["losses_150k"]), S):
            ax.barh(yi, gval, left=left, height=0.55, color=col, edgecolor=T["surface"], linewidth=2)
            left += gval
        ax.text(left + 0.1, yi, f"{left:.1f} W   eta {100*row['eta_150k']:.2f} %", va="center", fontsize=8.5, color=T["text"])
    ax.set_yticks(y)
    ax.set_yticklabels([f"{n}  ({tc[n]['tech']}, {int(tc[n]['vds'])} V)" for n in names], fontsize=8.5)
    ax.set_xlabel("Total loss [W] at 36 V -> 48 V, 75 % load (300 W), same topology, 150 kHz")
    ax.set_title("Si vs GaN vs SiC in the same converter")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(ax.get_xlim()[1], 16))
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in S[:6]]
    fig.legend(handles, [n for n, _ in LOSS_GROUPS], loc="lower center", fontsize=7.5, ncols=6, bbox_to_anchor=(0.5, -0.12))
    fig.text(0.01, -0.18, "No SiC MOSFET exists near 100 V; the 650 V parts are shown to make the point. Their low-voltage Qoss is "
             "extrapolated from 400 V data (estimate).", fontsize=7.2, color=T["text2"])
    _save(fig, "device_compare")


def weighted():
    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    v = [w["vin"] for w in R["weighted"]]
    ax.plot(v, [100 * w["cec"] for w in R["weighted"]], color=S[0], label="CEC weighted")
    ax.plot(v, [100 * w["euro"] for w in R["weighted"]], color=S[1], label="European weighted")
    ax.set_xlabel("Panel voltage [V]")
    ax.set_ylabel("Weighted efficiency [%]")
    ax.set_title("Solar-weighted efficiency (model): light-load points pull the weighted number down")
    ax.legend(loc="lower right")
    _save(fig, "weighted_eff")


def sc_rout():
    import numpy as np
    f = np.logspace(3, 8, 200)
    c, r = 10e-6, 10e-3
    exact = [sc.simulate_series_parallel(48, 23.5, c, r, x)["r_out"] for x in f]
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    ax.loglog(f, [sc.r_ssl([0.5], [c], x) for x in f], color=S[0], label="slow-switching limit 1/(4Cf)")
    ax.loglog(f, [sc.r_fsl([0.5] * 4, [r] * 4)] * len(f), color=S[1], label="fast-switching limit 2R")
    ax.loglog(f, exact, color=T["text"], lw=1.2, ls="-", label="exact (simulated)")
    ax.set_xlabel("Switching frequency [Hz]")
    ax.set_ylabel("Output resistance [ohm]")
    ax.set_title("2:1 series-parallel switched-capacitor converter: Rout vs f (C = 10 uF, R = 10 mOhm)")
    ax.legend()
    _save(fig, "sc_rout")


def topology_map():
    """Kilovolts down to phone-level: verified demonstrations, each a Vout..Vin span at its power."""
    items = [
        # (label, vlo, vhi, power W, class index, eta text)
        ("SiC DC transformer 7 kV -> 400 V (Rothmund 2019)", 400, 7000, 25e3, 0, "99.0 %"),
        ("Piezo, 4 in parallel, 450 -> 220 V (Stolt 2023)", 220, 450, 3.2e3, 1, "97.7 %"),
        ("CoBB bidirectional-GaN 200-500 -> 270 V (Aron 2025)", 200, 500, 880, 2, "95.4-97.5 %*"),
        ("GaN 4-switch optimizer 15-80 V (TI TIDA-010949)", 15, 80, 600, 2, "99.0 %"),
        ("This repo: hybrid 3-level GaN 12-60 -> 48 V", 12, 60, 400, 4, "model"),
        ("SC + buck-boost PV 30 -> 200 V (Liang 2012)", 30, 200, 240, 3, "92.5 %"),
        ("Hybrid SC 48 -> 1 V point-of-load (Das & Le 2019)", 1, 48, 30, 3, "90.9 %"),
        ("Piezo 100-200 -> 40-80 V (Boles 2021)", 40, 200, 15, 1, ">99 % calc., up to ~25 W"),
        ("Hybrid piezo + flying caps 48 -> 4.8 V (Ko 2026)", 4.8, 48, 0.72, 1, "96.2 %"),
    ]
    classes = ["SiC resonant DC transformer", "Piezoelectric resonator (magnetics-less)", "GaN buck-boost",
               "Hybrid switched-capacitor", "This design (predicted)"]
    fig, ax = plt.subplots(figsize=(9.4, 5.0))
    for lab, lo, hi, p, k, eta in items:
        ax.plot([lo, hi], [p, p], color=S[k], lw=6, solid_capstyle="round")
        ax.text(hi * 1.25, p, f"{lab}  [{eta}]", va="center", fontsize=7.6, color=T["text"])
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.8, 3e5)
    ax.set_ylim(0.3, 8e4)
    ax.set_xlabel("Voltage span covered (output ... input) [V]")
    ax.set_ylabel("Demonstrated power [W]")
    ax.set_title("Topology map: kilovolts to phone-level, with verified demonstrations")
    for v, lab in ((3.7, "phone cell"), (48, "48 V bus"), (400, "EV / PV string"), (7000, "medium voltage")):
        ax.axvline(v, color=T["grid"], lw=1)
        ax.text(v, 7.5e4, lab, rotation=90, fontsize=7, color=T["muted"], ha="right", va="top")
    handles = [plt.Line2D([0], [0], color=S[i], lw=6) for i in range(5)]
    fig.legend(handles, classes, loc="lower center", ncols=3, fontsize=7.5, bbox_to_anchor=(0.5, -0.1))
    ax.text(0.9, 0.34, "* excludes gate drive. Every figure is cited with its test conditions in docs/REFERENCES.md.",
            fontsize=7, color=T["text2"])
    _save(fig, "topology_map")


def hero_gif():
    """Topology -> solar input sweep -> loss budget + efficiency curve form -> flagship."""
    vins = R["vins"]
    pts = R["curves"]["0.75"]
    fig = plt.figure(figsize=(8.0, 3.8))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.55, 1])
    ax = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    n_sweep = len(vins)
    n_intro = 5
    n_frames = n_intro + n_sweep + 10
    fig.subplots_adjust(bottom=0.24, top=0.80)
    fig.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in S[:6]], [n for n, _ in LOSS_GROUPS],
               loc="lower center", ncols=6, fontsize=6.5, bbox_to_anchor=(0.5, 0.0))

    def draw(fr):
        ax.clear()
        ax2.clear()
        ax2.axis("off")
        if fr < n_intro:
            fig.suptitle("1  Pick a topology", x=0.02, ha="left", fontsize=11, weight="semibold")
            for i, (name, on) in enumerate((("buck", False), ("boost", False), ("buck-boost (4-switch)", False),
                                            ("switched-capacitor 2:1", False),
                                            ("hybrid 3-level flying-capacitor buck-boost, GaN", True))):
                ax.text(0.02, 0.85 - i * 0.17, ("> " if on and fr >= 2 else "   ") + name, transform=ax.transAxes,
                        fontsize=10, weight="semibold" if on and fr >= 2 else "normal",
                        color=T["text"] if (on and fr >= 2) else T["text2"])
            ax.axis("off")
            return
        ax.axis("on")
        k = min(fr - n_intro, n_sweep - 1)
        fig.suptitle("2  Sweep the solar input  ->  3  watch the loss budget and efficiency curve form" if fr < n_intro + n_sweep
                     else "4  The flagship reference design", x=0.02, ha="left", fontsize=11, weight="semibold")
        ax.set_xlim(10, 62)
        ax.set_ylim(96.5, 100)
        ax.set_xlabel("Panel voltage [V]")
        ax.set_ylabel("Efficiency [%]")
        ax.grid(True)
        xs = vins[: k + 1]
        ys = [100 * p["eta"] for p in pts[: k + 1]]
        ax.plot(xs, ys, color=S[0])
        ax.plot(xs[-1], ys[-1], "o", color=S[0], ms=8, mec=T["surface"], mew=2)
        p = pts[k]
        mode = p["label"].replace("buckboost", "buck-boost")
        ax.set_title(f"{xs[-1]:.0f} V -> 48 V, 75 % load   mode: {mode}   {p['fs']/1e3:.0f} kHz", fontsize=9)
        vals = [v for _, v in group_losses(p["losses"])]
        ax2.pie(vals, colors=S[:6], startangle=90, counterclock=False,
                wedgeprops={"width": 0.36, "edgecolor": T["surface"], "linewidth": 2})
        ax2.text(0, 0.07, f"{sum(vals):.2f} W", ha="center", fontsize=13, weight="semibold")
        ax2.text(0, -0.17, "loss budget", ha="center", fontsize=8, color=T["text2"])
        if fr >= n_intro + n_sweep:
            ax.text(11, 96.7, "Hybrid three-level GaN buck-boost, bidirectional-GaN bypass\n"
                    "CEC-weighted (model) %.2f %% at 36 V" % (100 * [w for w in R["weighted"] if w["vin"] == 36][0]["cec"]),
                    fontsize=8.5, color=T["text"], weight="semibold")

    anim = FuncAnimation(fig, draw, frames=n_frames, interval=180)
    anim.save(IMG / "hero.gif", writer=PillowWriter(fps=6), dpi=90)
    plt.close(fig)


if __name__ == "__main__":
    eff_vs_vin()
    loss_budget()
    device_compare()
    weighted()
    sc_rout()
    topology_map()
    hero_gif()
    print("charts written to", IMG)
