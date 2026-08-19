# AGENTS.md

## Cursor Cloud specific instructions

### Current repository state

- `webmedia-dl` is currently a **greenfield repository**. It contains only `README.md`, `LICENSE`, and a Node-oriented `.gitignore` — there is **no application code, no dependency manifest, and no tests yet**.
- Because there is no manifest, there is nothing to build, lint, test, or run end-to-end yet. Once source is added, document its lint/test/build/run commands here (or point to `package.json` scripts / a Makefile) rather than duplicating them.
- The `.gitignore` is GitHub's Node template (mentions Next.js, Vite, Nuxt, SvelteKit, pnpm/yarn), so the intended stack is **JavaScript/TypeScript on Node**. The repo name (`webmedia-dl`) suggests a web media downloader.

### Preinstalled toolchains (on the VM base image)

- Node `v22.14.0`, npm `10.9.7`, pnpm `10.33.3`, yarn `1.22.22` (classic), `corepack`, `nvm`.
- Python `3.12.3` is present, but `uv` and `bun` are **not** installed. If the project adopts a Python or Bun stack, add the installer to the update script.

### Dependency install (update script) behavior

- The startup update script auto-detects the manifest and is a safe no-op while the repo is empty:
  - `pnpm-lock.yaml` → `pnpm install --frozen-lockfile`
  - `package-lock.json` → `npm ci`
  - `yarn.lock` → `yarn install --frozen-lockfile`
  - `package.json` only → `npm install`
  - `uv.lock` (and `uv` installed) → `uv sync`
- To activate dependency installs, add the corresponding manifest/lockfile. If you introduce a package manager whose lockfile isn't listed above (e.g. Bun) or a Python stack needing `uv`, update the startup update script accordingly.
