"""Tune every MPPT algorithm the same way, so the benchmark compares methods, not tuning effort.

Each algorithm gets a small grid over its two most important parameters. Every combination
runs on the TUNING profile (watt_forge/control/profiles.py::tuning, never used for scoring)
with two noise seeds. The best mean dynamic MPPT efficiency wins. The winners are written to
data/mppt_tuned.json, and the algorithm classes are constructed with them (mppt.make(tuned=True)).

    python scripts/tune_mppt.py          # ~3 minutes on two cores
"""
from __future__ import annotations

import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from watt_forge import pv  # noqa: E402
from watt_forge.control import bench, mppt as M, profiles as PR  # noqa: E402

GRIDS = {
    # second pass: grids re-centred so that no winner sits on a grid edge (first-pass edges noted)
    "po": {"step": [0.1, 0.15, 0.2, 0.3], "period": [1, 2]},
    "vspo": {"gain": [0.02, 0.04, 0.08], "step_min": [0.2, 0.3, 0.45, 0.6]},
    "inc": {"step": [0.2, 0.3, 0.5], "tol": [0.0, 0.001, 0.003, 0.01]},
    "vsinc": {"gain": [0.04, 0.08, 0.16], "step_min": [0.2, 0.3, 0.45, 0.6]},
    "focv": {"k": [0.82, 0.84, 0.86, 0.88], "every": [500, 1000, 2000]},
    "esc": {"amp": [0.6, 0.8, 1.2], "gain": [0.008, 0.016, 0.032]},
    "pso": {"w": [0.3, 0.4, 0.6], "restart": [0.25, 0.35, 0.5]},
    "scan": {"points": [8, 10, 12, 14], "drop": [0.4, 0.45, 0.5]},
}
SEEDS = (101, 202)


_CACHE = {}


def _shared():
    """One panel, oracle (its P_mpp grids are the slow part), table and profile per worker."""
    if not _CACHE:
        panel = pv.Panel()
        _CACHE.update(panel=panel, oracle=bench.MppOracle(panel), eta=bench.EtaTable(), prof=PR.tuning())
    return _CACHE["panel"], _CACHE["oracle"], _CACHE["eta"], _CACHE["prof"]


def score(job):
    key, params = job
    panel, o, e, prof = _shared()
    vals = [bench.run(M.make(key, **params), prof, seed=s, oracle=o, eta=e, panel=panel)["eta_mppt"] for s in SEEDS]
    return key, params, sum(vals) / len(vals)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated keys to re-tune; others are kept from the file")
    only = [k for k in ap.parse_args().only.split(",") if k]
    out = ROOT / "data" / "mppt_tuned.json"
    jobs = []
    for key, grid in GRIDS.items():
        if only and key not in only:
            continue
        names = list(grid)
        for combo in itertools.product(*(grid[n] for n in names)):
            jobs.append((key, dict(zip(names, combo))))
    with Pool(2) as pool:
        results = pool.map(score, jobs)
    best = json.loads(out.read_text())["best"] if (only and out.exists()) else {}
    for key in only:
        best.pop(key, None)
    for key, params, val in results:
        if key not in best or val > best[key]["eta_tuning"]:
            best[key] = {"params": params, "eta_tuning": round(val, 6)}
    doc = {"_about": "Per-algorithm parameters chosen by scripts/tune_mppt.py on the tuning profile "
                     "(not used for scoring): a grid of 8-12 combinations per algorithm, same seeds for all. "
                     "Grids were re-centred over several passes until each winner was bracketed by lower-scoring "
                     "values (PSO restart across two passes) or sat at a physical floor (P&O period 1, an 8-point scan).",
           "grids": GRIDS, "seeds": list(SEEDS), "best": best}
    doc["best"] = {k: doc["best"][k] for k in GRIDS if k in doc["best"]}
    out.write_text(json.dumps(doc, indent=1) + "\n")
    for k, v in best.items():
        print(f"{k:6s} {100 * v['eta_tuning']:.3f} %  {v['params']}")


if __name__ == "__main__":
    main()
