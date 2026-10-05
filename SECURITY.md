# Security policy

## Supported versions

Security fixes go into the latest release and `main`.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead: the repository's **Security** tab, then **Report a vulnerability**. You will get an acknowledgement, and a fix or an explanation, as soon as practical.

Useful reports include the affected file or page, a minimal reproduction (for example a netlist or design JSON), and the impact you observed.

## Scope

In scope:
- the static web app (`docs/`), including its Content Security Policy, service worker, and the parsing of imported designs and formulas;
- the desktop app (`desktop/`): the netlist guard, the ngspice sandbox, design storage and Tauri capabilities;
- the build and release pipeline (`.github/workflows/`, signed releases, SBOM).

Out of scope: the physical safety of hardware built from these designs. That is covered by [SAFETY.md](SAFETY.md): the repository is a design and simulation reference, not a build guide.

The threat model and every trust boundary are described in [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).
