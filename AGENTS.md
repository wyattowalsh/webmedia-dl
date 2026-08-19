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

### Agent tooling: wyattowalsh/agents bundle (skills + its own MCPHub)

The startup update script restores the `wyattowalsh/agents` skill bundle globally for Cursor (non-fatal / `|| true`, so it never blocks pod boot). Fresh VMs do not persist `$HOME`, so it is reinstalled on each boot:

- **`wyattowalsh/agents` skills** — installed with `npx skills add github:wyattowalsh/agents -g -y -a cursor -s '*'`. Skills land in `~/.agents/skills/` (lock file `~/.agents/.skill-lock.json`) and are registered for the Cursor agent. Verify with `npx skills list -g`. Note: skills discovered from `~/.agents/skills` are picked up at agent-session start, so a session already running when they are (re)installed will not see them until the next session.

**MCPHub is intentionally NOT installed as a standalone/global package here.** It does not need its own hub — MCPHub is owned by the `wyattowalsh/agents` repo, and you connect to that one. Key facts (see the repo's `mcp/mcphub/README.md`, `scripts/mcphub/`, `.cursor/mcp.json`, and the `mcphub-operator` skill):

- The agents repo runs the hub on demand via `npx @samanhappy/mcphub@<pinned>` (e.g. `1.0.24`) bound loopback-only on `127.0.0.1:46683`, using `mcp/mcphub/mcp_settings.json` — there is no `npm install -g` step.
- Clients (Cursor) connect to `http://127.0.0.1:46683/mcp/<group>` (default group: `harness`) with `Authorization: Bearer ${MCPHUB_BEARER_TOKEN}`, either via the repo's `.cursor/mcp.json` (`type: http`) or the `scripts/mcphub/remote-stdio.sh` bridge in the repo's root `mcp.json` (the bridge auto-starts the hub via `scripts/mcphub/ensure-running.sh`, so no separate start command is needed).
- Secrets are **local, not external**: `ADMIN_PASSWORD`, `JWT_SECRET`, and `MCPHUB_BEARER_TOKEN` are generated locally into `.env.mcphub` (`mcp/mcphub/README.md` shows the `secrets.token_urlsafe` recipe). The hub is loopback-only and single-user.
- Several `harness` servers are keyless (DDGS, Fetch, Wikipedia, DeepWiki, llms.txt catalog); others (Brave, Context7, Tavily, Exa, …) need API keys in `.env.mcphub` and stay disabled without them. The hub itself starts and authenticates regardless. This repo's design is macOS-first (`just mcphub-up`, launchd), but the core `npx @samanhappy/mcphub` hub also comes up on Linux.
