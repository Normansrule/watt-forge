# Contributing to Watt Forge

Thanks for helping. Watt Forge is a teaching and design reference, so the bar is **correctness you can check**. Every equation has a worked example in the tests, every efficiency figure cites its source with test conditions, and every algorithm behaves the same in Python, JavaScript and C.

## Ground rules

- **Safety first.** This repository is a design and simulation reference. Contributions must not present it as a build-and-energize guide, and hardware changes keep the warnings in [SAFETY.md](SAFETY.md).
- **Cite with conditions.** A new efficiency or performance figure goes into `data/references.json` with its DOI or URL, the exact test conditions, and a `status` saying how you verified it. Never present a best-case lab number as typical.
- **Python is canonical.** Physics and control live in `watt_forge/`. The browser ports in `docs/js/model/` and the C references in `hardware/flagship/control/` must reproduce it, and the parity tests enforce that. Change all three together.
- **Generated files are generated.** Edit `site/*.html`, not `docs/*.html`, and edit `data/references.json`, not `docs/REFERENCES.md`. Then run `make data site` (or the specific script) and commit the result. CI fails if generated files are stale.

## Setup and checks

```bash
python3 -m pip install --require-hashes -r requirements.lock && python3 -m pip install --no-deps -e .
sudo apt-get install ngspice iverilog          # optional: enables the ngspice and HDL tests
make test                                      # pytest, JS parity and guard checks, Rust tests
python3 -m http.server -d docs 8000            # the site at http://localhost:8000
```

The control-library data takes about 10 minutes to regenerate (`python scripts/make_control_data.py`). Tuning the MPPT parameters (`python scripts/tune_mppt.py`) changes the benchmark, so rerun both.

## Pull requests

1. Open an issue first for anything larger than a fix, so we can agree on the approach.
2. Keep each pull request to one topic. Add or update tests: a worked example for new physics, a parity case for a new port, a behaviour test for a new controller.
3. `make test` passes locally, and `git diff` after `make check-generated` is empty.
4. Describe what you verified and how (sources, tests, simulations).

## Code style

- Python: standard library first, type hints on public functions, no new runtime dependencies without discussion.
- JavaScript: plain ES modules, no build step, no npm runtime dependencies. Never `eval`, `new Function` or `innerHTML` with data. The site's Content Security Policy forbids them anyway.
- C: C99, `-Wall -Wextra -Werror` clean, no dynamic allocation, double precision unless re-validated.

By contributing you agree that your contribution is licensed under the MIT License and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
