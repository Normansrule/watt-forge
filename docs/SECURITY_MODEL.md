# Security model

Watt Forge is a static, local-first web app with an optional desktop shell. This page covers what it trusts and how it treats everything else.

## Assets and boundaries

| Boundary | What crosses it | Treatment |
|---|---|---|
| Browser to network | nothing at runtime | Every page carries a Content Security Policy: `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' ipc: http://ipc.localhost; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'self'`. There are no third-party scripts, fonts, analytics or trackers. The `ipc:` origins exist only inside the desktop app (the Tauri IPC channel) and match nothing on the web. The only network reads are the offline service worker (`docs/sw.js`) fetching the site's own files; it ignores every request to another origin. `tests/test_web.py` enforces this on every page and every JS file. |
| User to app (typed input) | numbers, a target-curve formula | Numeric fields are range-checked. The validator's formula goes through a tokenizer and shunting-yard parser over a whitelist of operators and functions (`docs/js/model/expr.js`). Strings are never passed to `eval`, `new Function`, `innerHTML` or `setAttribute('style')`; the parity test also checks that names like `constructor` and `__proto__` are rejected. |
| File to app (imported design JSON) | untrusted JSON | 10 kB cap; `validateDesign` accepts only known fields, own properties only, with numbers in physical ranges. Anything else is rejected with a message naming the field. |
| App to storage | saved designs | `localStorage` under the `wattforge:` prefix, wrapped so blocked storage never breaks the page. It is per browser, never sent anywhere, and clearing site data removes it. |
| Netlist to simulator (desktop) | untrusted SPICE netlists | See the next section. |
| Browser cache (installable web app) | the site's own files | `sw.js` precaches the site under a cache name derived from a hash of every file, so a new deploy replaces the old cache. It handles same-origin `GET` requests only, and registers only over HTTPS or on localhost, never inside the desktop app. |
| SPICE runner page (web) | an edited netlist | Checked by the JavaScript port of the guard for feedback only. The web version never executes a netlist; it shows ngspice results stored at build time for unmodified presets. |

## Malicious netlists (desktop and Python runner)

ngspice is a powerful program. A netlist can contain a `.control` block with `shell` commands, write files (`write`, `wrdata`), or read arbitrary files (`.include`, `.lib`). Imported netlists are therefore untrusted, and must pass a guard before ngspice sees them:

- **Rejected:**
  - `.control`/`.endc`, `.include`/`.inc`, `.lib`/`.endl`, `.exec`, `.csparam`, and any unknown dot command
  - the words `shell`, `system`, `exec`, `write`, `wrdata`, `wrs2p`, `load`, `source`, `cd`, `setcs`, `codemodel` and `osdi` anywhere, continuation lines included
  - element types outside `R C L V I S D E G F H B K X M Q J`
- **Resource limits:** 256 kB maximum and 20,000 lines; `.tran` may ask for at most 5 million points.
- **Execution:** ngspice runs as `ngspice -b` in a fresh temporary directory with a cleared environment (only `PATH`), stdin closed and a 60 s wall-clock limit. Output is capped at 1 MB and the directory is deleted afterwards.
- **Three implementations, one rule set:** `watt_forge/spice.py::check_netlist` (Python), `desktop/netlist-guard` (Rust, no dependencies; the one that gates ngspice in the desktop app) and `docs/js/model/netlist-guard.js` (browser feedback only). All three are run against one shared case file, `tests/fixtures/guard_cases.txt`, by `pytest`, `cargo test` and `node tests/js/guard.mjs`.

## Desktop shell (Tauri 2)

- **Capabilities:** `core:default` only. No filesystem, shell, HTTP, opener or updater plugins are installed.
- **Native commands:** five app-defined commands: `save_design`, `list_designs`, `load_design`, `simulate_netlist`, and `smoke_report`, which does nothing unless the app was started with `WATTFORGE_SMOKE=1` (the CI end-to-end test).
- **Design storage:** confined to `<app data>/designs/`, with file names restricted to `[A-Za-z0-9 _-]{1,64}`, contents parsed as JSON before writing, and a 10 kB cap.
- **No inbound network, offline after install:** the window loads the bundled `docs/` and the CSP allows only `'self'` and the IPC channel. `freezePrototype` is on.
- **Build status:** built and packaged (`.deb`, `.rpm`, `.AppImage`) on Ubuntu 24.04. The smoke test passed: the page called `simulate_netlist` over IPC, the guard rejected a `.control`/`shell` netlist, and ngspice measured the RC check at 12.000 V. CI repeats the smoke test on every desktop build. The Windows and macOS installers are built by CI only.

## Supply chain (OWASP Top 10 2025, A03 Software Supply Chain Failures)

- **Pinned dependencies:**
  - Python: `requirements.lock`, exact versions with SHA-256 hashes (`pip install --require-hashes`).
  - Rust: `Cargo.lock` is committed.
  - Web: the site has **zero** npm dependencies.
- **Pinned CI:** every GitHub Action is pinned by full commit SHA, with the tag in a comment. Dependabot proposes updates for Actions, pip and cargo.
- **Least-privilege workflows:** `permissions: contents: read` by default. Only `release` gets `contents: write` and `id-token: write`, and checkout runs with `persist-credentials: false`.
- **Scanning:** CodeQL (Python, JavaScript, Actions) on push, pull request and weekly; gitleaks on every push.
- **Releases:**
  - a source ZIP and an SPDX SBOM (`anchore/sbom-action`)
  - `SHA256SUMS`
  - Sigstore-signed build provenance (`actions/attest-build-provenance`), verifiable with `gh attestation verify <file> --repo <owner>/<repo>`

## Not in scope

- Physical safety of hardware built from the reference design. See [SAFETY.md](../SAFETY.md).
- The reference C and Verilog are not production firmware: no watchdog, no secure boot, no field update.

## Reporting

Open a private security advisory on the repository (Security, then Report a vulnerability).
