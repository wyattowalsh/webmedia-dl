# AGENTS.md

## Cursor Cloud specific instructions

### Stack

- Python **3.13** worker and CLI (`webmedia_dl` / `webmedia-dl`) managed with **uv**.
- Browser capture extensions under `extensions/` (vanilla JS modules).
- Swift packages under `apps/` for Apple clients. GitHub `macos-15` CI runs
  Core `swift test`, builds the Mac package, and typechecks the remaining
  Apple packages. Linux workers do not compile Swift. Device UI, signing,
  and store submission stay BLOCKED.
  Shells: `WebMediaDLMac`, `WebMediaDLiOS`, `WebMediaDLiPadOS`, `WebMediaDLVision`,
  `WebMediaDLWatch`, `WebMediaDLTV`, plus `WebMediaDLCore`.

### Commands

| Task | Command |
|---|---|
| Install | `uv sync --locked` |
| CLI | `uv run webmedia-dl --help` |
| Doctor | `uv run webmedia-dl doctor` |
| Tests | `uv run pytest` / `uv run pytest --cov` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |
| Types | `uv run ty check` |
| Schemas | `uv run python -m webmedia_dl.schema_export` |
| Bundle | `uv run python scripts/validate_bundle.py` |
| Apple packages (macOS) | `bash scripts/build_apple_packages.sh` |
| Extension tests | `node --test tests/unit/extensions/*.mjs` |
| Sync extension trees | `uv run python scripts/sync_browser_extensions.py` |
| Extension zips | `uv run python scripts/package_extensions.py` |
| Pack zip | `uv run python scripts/package_bundle.py` |

If `uv` is missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

### Invariants

- A source URL never becomes a filesystem path.
- A display title never becomes artifact identity.
- A provider never receives arbitrary user arguments.
- Source artifacts are immutable after registration.
- Derivatives do not publish before mandatory validation.
- Restricted profiles cannot delegate disallowed work.
- Browser extensions are not native command runners.
- Planned or simulated checks never become runtime `PASS`.
- No DRM circumvention, default telemetry, silent cookies, or automatic provider installs.

`wmdl` is a personal alias only — never the public command name.

### Preinstalled toolchains (on the VM base image)

- Node `v22.14.0`, npm `10.9.7`, pnpm `10.33.3`, yarn `1.22.22` (classic), `corepack`, `nvm`.
- Python `3.12.3` is present on the image; this project uses **uv**-managed **CPython 3.13**.
- `uv` is not preinstalled; install it in the update script when missing.

### Dependency install (update script) behavior

- `pnpm-lock.yaml` → `pnpm install --frozen-lockfile`
- `package-lock.json` → `npm ci`
- `yarn.lock` → `yarn install --frozen-lockfile`
- `package.json` only → `npm install`
- `uv.lock` → install `uv` if needed, then `uv sync --locked`

### Agent tooling: wyattowalsh/agents bundle (skills + its own MCPHub)

The startup update script restores the `wyattowalsh/agents` skill bundle globally for Cursor (non-fatal / `|| true`). MCPHub is **not** installed standalone; connect to the hub from `wyattowalsh/agents`.
