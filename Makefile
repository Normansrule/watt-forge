# Watt Forge -- one entry point for building and checking everything.
PY ?= python3

.PHONY: all install data control tune spice icons figures site test test-py test-js test-rust desktop desktop-dev check-generated zip clean

all: data figures site test

install:            ## exact, hash-checked Python dependencies (+ the package itself, editable)
	$(PY) -m pip install --require-hashes -r requirements.lock
	$(PY) -m pip install --no-deps -e .

data:               ## run the design exploration, regenerate data/*.json, web data and fixtures
	$(PY) -m watt_forge.flagship.design
	$(PY) scripts/make_web_data.py
	$(PY) scripts/make_artifacts.py

control:            ## MPPT benchmark, efficiency controls, daily energy, parity fixture (~10 min, 2 cores)
	$(PY) scripts/make_control_data.py

tune:               ## re-tune every MPPT tracker on the tuning profile (then run `make control`)
	$(PY) scripts/tune_mppt.py

spice:              ## re-run the SPICE runner presets in ngspice (needs ngspice on PATH)
	$(PY) scripts/make_spice_presets.py

icons:              ## raster icons for the installable web app and the desktop app
	$(PY) scripts/make_icons.py

figures:            ## README/site charts, hero GIF, animated schematics
	$(PY) scripts/make_charts.py
	$(PY) scripts/make_diagrams.py

site:               ## wrap site/*.html fragments into docs/
	$(PY) scripts/build_site.py

test: test-py test-js test-rust

test-py:            ## physics, flagship model vs circuit sim vs ngspice, C vs Python controller, HDL testbench, site checks
	$(PY) -m pytest

test-js:            ## browser models == Python models (physics, netlist guard, control library)
	node tests/js/parity.mjs
	node tests/js/guard.mjs
	node tests/js/control.mjs

test-rust:          ## netlist guard used by the desktop app
	cd desktop/netlist-guard && cargo test --quiet

desktop:            ## build the desktop installers (needs Rust, tauri-cli and the Tauri system packages; see desktop/README.md)
	cd desktop/src-tauri && cargo tauri build

desktop-dev:        ## run the desktop app without installing it
	cd desktop/src-tauri && cargo tauri dev

check-generated:    ## fail if committed generated files are stale
	$(MAKE) data site
	git diff --exit-code -- data docs/data docs/js/data docs/REFERENCES.md tests/fixtures docs/*.html docs/learn docs/tools docs/sw.js docs/manifest.webmanifest

zip:                ## repository ZIP without caches (what the publish script expects)
	$(PY) scripts/make_zip.py

clean:
	rm -rf build .pytest_cache desktop/netlist-guard/target desktop/src-tauri/target
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
