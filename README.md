# WebMedia DL

Local-first universal media acquisition and export for Apple devices and
desktop browsers.

> [!IMPORTANT]
> Display name **WebMedia DL**. Repository and CLI **`webmedia-dl`**.
> Python package **`webmedia_dl`**. Swift prefix **`WebMediaDL`**.
> `wmdl` is a personal alias only.

## Quick start

```bash
uv sync --locked
uv run webmedia-dl doctor
uv run webmedia-dl submit https://example.com/photo.png --data-dir /tmp/webmedia-dl-demo
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
python scripts/validate_bundle.py
```

The loopback worker binds `127.0.0.1` only:

```bash
uv run webmedia-dl serve --data-dir /tmp/webmedia-dl-demo
```

## Layout

| Path | Role |
|---|---|
| `src/webmedia_dl/` | Python worker, CLI, authenticated local API |
| `schemas/` | Shared JSON Schema contracts |
| `openspec/changes/build-webmedia-dl-v1/` | Proposed behavior change |
| `extensions/` | Safari / Chromium / Firefox capture (no native argv) |
| `apps/WebMediaDLCore/` | Swift package for Apple clients |
| `docs/` | ADRs, planning, privacy, release gates |
| `resources/` | Presets, policy profiles, tool catalog |

## Non-goals

No mandatory cloud backend, default telemetry, DRM circumvention,
automatic provider installation, or silent cookie access.

Read [`START_HERE.md`](START_HERE.md) for the planning pack order.
