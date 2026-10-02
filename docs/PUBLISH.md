# Publish Watt Forge: web app + desktop app

Two blocks, each pasted once into an Ubuntu terminal (WSL2 works).

- **Block 1 (required)** publishes everything. It pushes the repository and turns on GitHub Pages, which gives you the **web app**. It also tags a version, so GitHub Actions builds the **desktop app** for Linux, Windows and macOS and attaches the installers to a GitHub release.
- **Block 2 (optional)** installs the desktop app on this Ubuntu machine. It downloads the `.deb` from that release, or builds it locally if the release isn't ready yet.

## Block 1: publish the web app and the desktop release

Edit only the variables at the top. The only interactive step is `gh auth login` the first time. A one-time scope refresh may also ask you to confirm in the browser: GitHub requires the `workflow` scope to push `.github/workflows`.

What it does, in order:

1. Installs `git`, the GitHub CLI (`gh`) and `unzip` with apt. This is the only `sudo`.
2. Logs in to GitHub if needed, with the `workflow` scope.
3. Finds `watt-forge.zip` in `~/Downloads`, or in the Windows Downloads folder under WSL. It unzips into `~/projects/<repo>`, never into your home folder itself.
4. Commits, creates the GitHub repository, pushes to `main` and enables GitHub Pages from `/docs`.
5. Tags `VERSION` and pushes the tag. The `release` workflow then builds the installers, which takes about 15–25 minutes.
6. Prints the web app URL and the release URL.

It is safe to re-run. Existing repos, remotes, Pages settings and tags are reused, and a re-run with a newer ZIP commits only what changed. To ship a new desktop build later, set `VERSION` to the next number (for example `v0.1.1`) and paste again.

```bash
GH_USER="Normansrule"                    # your GitHub username
REPO="watt-forge"                        # repository name to create
GIT_NAME="Aleksander Norman"             # name for the commit
GIT_EMAIL="aleksanderjnorman@gmail.com"  # email for the commit
VERSION="v0.1.0"                         # desktop release tag; bump it to ship a new desktop build
(
set -euo pipefail
# 1. Install git, the GitHub CLI and unzip (the only sudo in this script)
sudo apt-get update -y && sudo apt-get install -y git gh unzip
# 2. Log in to GitHub (interactive the first time; asks for the workflow scope needed to push CI files)
gh auth status --hostname github.com >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol https --web --scopes workflow
# 3. Make sure the login can push workflow files, and that it is the account named above
gh auth status --hostname github.com 2>&1 | grep -q "workflow" || gh auth refresh --hostname github.com --scopes workflow
[ "$(gh api user -q .login)" = "$GH_USER" ] || gh auth switch --hostname github.com --user "$GH_USER"
# 4. Let git use the gh login for HTTPS pushes
gh auth setup-git --hostname github.com
# 5. Find the ZIP: ~/Downloads first, then the Windows Downloads folder under WSL
ZIP="$HOME/Downloads/watt-forge.zip"; [ -f "$ZIP" ] || ZIP="$(ls -t /mnt/c/Users/*/Downloads/watt-forge*.zip 2>/dev/null | head -1 || true)"
[ -n "$ZIP" ] && [ -f "$ZIP" ] || { echo "watt-forge.zip not found in ~/Downloads or the Windows Downloads folder"; exit 1; }
# 6. Unzip into ~/projects/$REPO (never into ~ itself; existing files are updated in place)
DEST="$HOME/projects/$REPO"; [ "$DEST" != "$HOME" ] && mkdir -p "$DEST" && TMP="$(mktemp -d)" && unzip -q -o "$ZIP" -d "$TMP" && cp -a "$TMP"/watt-forge/. "$DEST"/ && rm -rf "$TMP"
# 7. Enter the project and confirm it is the right folder
cd "$DEST" && [ -f watt_forge/flagship/model.py ] && [ -f desktop/src-tauri/tauri.conf.json ] || { echo "unexpected folder contents in $DEST"; exit 1; }
# 8. Create the repository locally on branch main (only the first time)
[ -d .git ] || git init -b main
# 9. Set the commit identity for this repository only
git config user.name "$GIT_NAME" && git config user.email "$GIT_EMAIL"
# 10. Commit everything (first commit, or only what changed on a re-run)
git add -A && { git diff --cached --quiet || git commit -m "Watt Forge: converter design platform (web + desktop) and hybrid GaN buck-boost reference design"; }
# 11. Create the GitHub repository if it does not exist yet
gh repo view "$GH_USER/$REPO" >/dev/null 2>&1 || gh repo create "$GH_USER/$REPO" --public --description "Converter design from first principles: loss models, tools, a hybrid GaN buck-boost reference design. Web app + desktop app."
# 12. Point origin at it (works on re-runs too)
git remote add origin "https://github.com/$GH_USER/$REPO.git" 2>/dev/null || git remote set-url origin "https://github.com/$GH_USER/$REPO.git"
# 13. Push to main
git push -u origin main
# 14. Web app: enable GitHub Pages from /docs on main (create, or update if already enabled)
gh api -X POST "repos/$GH_USER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 || gh api -X PUT "repos/$GH_USER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null
# 15. Desktop app: tag this version (skipped if the tag already exists) ...
git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null || git tag -a "$VERSION" -m "Watt Forge $VERSION"
# 16. ... and push the tag, which starts the release workflow (Linux, Windows and macOS installers)
git ls-remote --exit-code --tags origin "refs/tags/$VERSION" >/dev/null 2>&1 || git push origin "$VERSION"
# 17. Print where both forms will appear (Pages takes 1-2 minutes; the desktop release about 15-25)
echo "Web app:      $(gh api "repos/$GH_USER/$REPO/pages" -q .html_url 2>/dev/null || echo "https://${GH_USER,,}.github.io/$REPO/")"
echo "Desktop app:  https://github.com/$GH_USER/$REPO/releases/tag/$VERSION   (build progress: https://github.com/$GH_USER/$REPO/actions)"
)
```

If a step fails, the block stops there and prints the error, and your terminal stays open. Fix the cause and paste the block again.

## Block 2 (optional): install the desktop app on this Ubuntu machine

Paste this after Block 1, in the same terminal or a new one. If the release from Block 1 already has its `.deb`, the block downloads and installs it in seconds. If not, the block builds the app here instead, which takes 10–20 minutes the first time. It installs Rust for your user, the Tauri CLI, and the Tauri system libraries.

The `.deb` declares ngspice as a dependency, so apt installs it too. On WSL2, Windows 11 shows the app window through WSLg.

```bash
GH_USER="Normansrule"                    # your GitHub username
REPO="watt-forge"                        # repository name
VERSION="v0.1.0"                         # release tag to install from
(
set -euo pipefail
# 1. System packages: ngspice, plus what a local build would need (the only sudo, apart from installing the .deb)
sudo apt-get update -y && sudo apt-get install -y gh curl build-essential pkg-config libssl-dev libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev patchelf file ngspice
# 2. Work in a fresh temporary folder
WORK="$(mktemp -d)"
# 3. Try the released .deb first (exists once the release workflow has finished)
if gh release download "$VERSION" --repo "$GH_USER/$REPO" --pattern "*_amd64.deb" --dir "$WORK" --clobber 2>/dev/null; then
  echo "Using the released installer from $VERSION"
else
  echo "Release $VERSION has no .deb yet: building locally"
  # 4. Rust for this user (rustup; no sudo), if missing
  command -v cargo >/dev/null 2>&1 || [ -x "$HOME/.cargo/bin/cargo" ] || curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
  . "$HOME/.cargo/env"
  # 5. The Tauri CLI, if missing (about 10 minutes the first time)
  cargo tauri --version >/dev/null 2>&1 || cargo install tauri-cli --version "^2" --locked
  # 6. Build the .deb from the project folder Block 1 created
  cd "$HOME/projects/$REPO/desktop/src-tauri" && cargo tauri build --bundles deb
  cp target/release/bundle/deb/*_amd64.deb "$WORK"/
fi
# 7. Install it (apt also pulls in its dependencies)
sudo apt-get install -y "$WORK"/*_amd64.deb
# 8. Clean up the temporary folder
rm -rf "$WORK"
# 9. Done: how to start it
echo "Installed. Start Watt Forge from your app menu, or run: watt-forge-desktop &"
)
```

## Updating later

- **Web app only (content changes):** download the new ZIP and paste Block 1 unchanged. Pages redeploys on the push, and the installed web app picks up the new files the next time it is online.
- **Desktop app too:** also bump `VERSION` (for example `v0.1.1`) in Block 1, then Block 2 with the same `VERSION`. The version shown inside the app comes from `desktop/src-tauri/tauri.conf.json`, so bump that file in the repo as well when you cut a real release.
