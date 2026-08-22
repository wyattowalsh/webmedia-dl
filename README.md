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
uv run webmedia-dl pause --queue --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl resume --queue --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl drop ./photo.png --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl paste https://example.com/photo.png --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl speak https://example.com/photo.png --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl provenance sha256:deadbeef --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl artifacts --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl package-extensions --dest /tmp/webmedia-dl-extensions
# also works from an installed wheel via packaged runtime/extensions
uv run webmedia-dl updates
uv run webmedia-dl support-bundle --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl plan https://example.com/watch --data-dir /tmp/webmedia-dl-demo
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
python scripts/validate_bundle.py
```

The loopback worker binds `127.0.0.1` only and runs accepted jobs from the queue:

```bash
uv run webmedia-dl serve --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl run-next --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl job <job-id> --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl history --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl cancel <job-id> --data-dir /tmp/webmedia-dl-demo
uv run webmedia-dl pair create --client-profile personal-restricted
uv run webmedia-dl pair confirm <pairing-id>
# confirm JSON includes session_key; iPhone/iPad/vision derive the same SHA256(nonce:mac-confirm) locally
# confirmed pairing keeps the client profile; the Mac worker runs heavy acquisition
uv run webmedia-dl companion capture https://example.com/a.mp4
uv run webmedia-dl policy
uv run webmedia-dl migrate-scan ./legacy
uv run webmedia-dl migrate-apply ./legacy
uv run webmedia-dl version
uv run webmedia-dl alias-note
```

## Layout

| Path | Role |
|---|---|
| `src/webmedia_dl/` | Python worker, CLI, authenticated local API |
| `schemas/` | Shared JSON Schema contracts |
| `openspec/changes/build-webmedia-dl-v1/` | Proposed behavior change |
| `extensions/` | Safari, Chrome, Brave, Edge, Chromium, Firefox capture (no native argv) |
| `apps/` | SwiftUI shells for macOS, iOS, iPadOS, visionOS, watchOS, tvOS plus `WebMediaDLCore`. Complete clients and the Mac app explain `POST /v1/plan` and `GET /v1/doctor`. GitHub `macos-15` compiles them; device runtime stays BLOCKED |
| `docs/` | ADRs, planning, privacy, release gates |
| `resources/` | Presets, policy profiles, tool catalog |

## Non-goals

No mandatory cloud backend, default telemetry, DRM circumvention,
automatic provider installation, or silent cookie access.

Read [`START_HERE.md`](START_HERE.md) for the planning pack order.
