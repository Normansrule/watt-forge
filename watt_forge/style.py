"""Shared chart styling (reference data-viz palette, validated for CVD separation)."""
from __future__ import annotations

LIGHT = {
    "surface": "#fcfcfb", "text": "#0b0b0b", "text2": "#52514e", "muted": "#8a8984", "grid": "#e8e7e3",
    "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
}
DARK = {
    "surface": "#1a1a19", "text": "#ffffff", "text2": "#c3c2b7", "muted": "#8f8e87", "grid": "#2f2f2d",
    "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
}

# Six loss groups (donuts stay at <= 6 segments; the full term list lives in tables/tooltips)
LOSS_GROUPS = [
    ("Switch conduction", ("switch_conduction", "cond_switch", "cond_diode", "circuit_resistive")),
    ("Switching", ("coss", "coss_hard", "overlap", "coss_hysteresis", "loop_ringing", "dead_time",
                   "dead_time_conduction", "reverse_recovery", "gate", "leakage_clamp")),
    ("Inductor", ("inductor_dcr", "inductor_ac", "inductor_core")),
    ("Capacitors", ("cfly_esr", "cin_cout_esr", "cap_esr")),
    ("Sense, copper, disconnect", ("shunts", "pcb_copper", "bds_disconnect", "bds_path")),
    ("Housekeeping", ("aux",)),
]


def group_losses(losses: dict) -> list:
    out = []
    for name, keys in LOSS_GROUPS:
        out.append((name, sum(losses.get(k, 0.0) for k in keys)))
    return out


def apply_mpl(theme=LIGHT):
    import matplotlib as mpl
    mpl.rcParams.update({
        "figure.facecolor": theme["surface"], "axes.facecolor": theme["surface"],
        "savefig.facecolor": theme["surface"], "axes.edgecolor": theme["grid"],
        "axes.labelcolor": theme["text2"], "xtick.color": theme["text2"], "ytick.color": theme["text2"],
        "text.color": theme["text"], "axes.grid": True, "grid.color": theme["grid"], "grid.linewidth": 0.8,
        "grid.linestyle": "-", "axes.spines.top": False, "axes.spines.right": False,
        "axes.titleweight": "semibold", "axes.titlesize": 12, "axes.titlelocation": "left",
        "font.size": 10, "lines.linewidth": 2.0, "lines.solid_capstyle": "round", "legend.frameon": False,
    })
