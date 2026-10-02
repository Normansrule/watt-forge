"""Package the repository as a ZIP for delivery / release (no .git, caches or build output).

    python scripts/make_zip.py [--out watt-forge.zip]
"""
from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "target", "build", "dist", ".ipynb_checkpoints", "gen"}
SKIP_SUFFIX = {".pyc", ".zip"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "watt-forge.zip"))
    ap.add_argument("--prefix", default="watt-forge")
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
            for f in sorted(filenames):
                p = Path(dirpath) / f
                if p.suffix in SKIP_SUFFIX or p.resolve() == out.resolve():
                    continue
                z.write(p, f"{a.prefix}/{p.relative_to(ROOT).as_posix()}")
                n += 1
    print(f"wrote {out} ({n} files, {out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
