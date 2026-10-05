# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-04

### Added
- **Control-algorithm library** (`watt_forge/control/`) with eight maximum power point tracking (MPPT) algorithms: perturb and observe (fixed and variable step), incremental conductance (fixed and variable step), fractional open-circuit voltage, extremum seeking (injected dither; ripple correlation control is the same principle using switching ripple), particle swarm, and global scan-and-track.
- **MPPT benchmark**: closed-loop plant with input-voltage-loop dynamics, sensor noise and 12-bit quantisation. Profiles are compressed EN 50530-style irradiance ramps, cloud edges, partial shading and steady light, scored by dynamic MPPT efficiency (EN 50530 definition) and energy delivered to the battery. Three noise seeds per result.
- **Comparable tuning**: each tracker's two key parameters are chosen by a grid search of 8 to 12 combinations on a separate tuning profile (`scripts/tune_mppt.py`). Grids were re-centred until each winner was bracketed by lower-scoring values (particle swarm's restart threshold across two passes) or sat at a physical floor.
- **Efficiency controls** on the flagship loss model. Adaptive switching frequency and adaptive dead time are online hill climbs limited to realistic measurement resolution and averaged over 20 noise trials. Burst mode accounts for its input-ripple MPPT mismatch, and bypass for pinning the panel at battery voltage. A daily energy waterfall shows where the energy goes.
- **Three-language parity**: JavaScript ports (`docs/js/model/mppt.js`, `effctl.js`) match Python to rounding error, and the C references (`hardware/flagship/control/wf_mppt.c`) match decision for decision.
- **Control lab** page: leaderboard, live races in a Web Worker, a tuning playground, the efficiency-control explorer and a day of sun. The control lesson was rewritten with all eight algorithms, their equations and references.
- 15 new verified references (MPPT, extremum seeking, efficiency control, EN 50530).
- An independent reviewer checked the new figures, equations and claims against the code and data, twice; the corrections it found are included.
- Section sub-navigation for lessons and tools, a structured footer, and self-hosted Inter and JetBrains Mono fonts (OFL). There are still no third-party requests.
- Community files: contributing guide, security policy, code of conduct, citation metadata, issue and pull-request templates.

### Changed
- The site's safety notice is now a one-line strip on every page (still on every page).
- GitHub Actions pins updated to the versions Dependabot proposed (still pinned by full commit SHA).

## [0.1.0] - 2026-10-02

### Added
- Seven lessons, six interactive tools, the flagship hybrid three-level GaN buck-boost reference design (schematic, BOM, loss model, circuit simulation, ngspice cross-check, C controller, Verilog modulator).
- Desktop app (Tauri 2) with a sandboxed ngspice runner, and installers for Linux, Windows and macOS on every release.
- Installable offline web app, signed releases with SBOM, checksums and Sigstore provenance.

[0.2.0]: https://github.com/Normansrule/watt-forge/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Normansrule/watt-forge/releases/tag/v0.1.0
