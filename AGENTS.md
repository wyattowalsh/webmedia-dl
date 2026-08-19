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

### Agent tooling: wyattowalsh/agents skills + MCPHub

The startup update script also restores two user-requested global tools (both non-fatal / `|| true`, so they never block pod boot). Fresh VMs do not persist `$HOME`, so these are reinstalled on each boot by the update script:

- **`wyattowalsh/agents` skills** — installed with `npx skills add github:wyattowalsh/agents -g -y -a cursor -s '*'`. All 67 skills land in `~/.agents/skills/` (lock file `~/.agents/.skill-lock.json`) and are registered for the Cursor agent. Verify with `npx skills list -g`. Note: skills discovered from `~/.agents/skills` are picked up at agent-session start, so a session already running when they are (re)installed will not see them until the next session.
- **MCPHub (`@samanhappy/mcphub`)** — installed into a user prefix (`~/.npm-global`) to avoid the root-owned global npm prefix (`/usr/lib/node_modules`, which causes `EACCES`). The update script symlinks `~/.npm-global/bin/mcphub` into the nvm global bin dir (`$(dirname "$(command -v npm)")`, already on `PATH`) so `mcphub` resolves in any fresh shell without editing `~/.bashrc`.

MCPHub run/verify notes (see also the [CLI guide](https://docs.mcphub.app/features/cli)):

- Start the hub: `PORT=<port> mcphub` (no-arg `mcphub` starts the server; a subcommand runs the CLI). It serves a dashboard + HTTP API and prints a one-time generated admin password to its log on first run.
- The CLI drives a running hub over HTTP: `mcphub login --url http://localhost:<port> --username admin --password <generated>`, then `mcphub servers add|list`, `mcphub tools list`, etc.
- Calling a tool requires a **bearer key** (`mcphub keys create --name <n> --access-type all`), not the admin JWT. The one-shot `mcphub call ...` does not perform the MCP streamable-HTTP `initialize` handshake, so a direct tool call must first `initialize` (to obtain an `mcp-session-id`), send `notifications/initialized`, then `tools/call` against `/mcp/<server>` (or `/mcp/$smart`).
