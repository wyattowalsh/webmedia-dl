# Validation report

| Gate | Status | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 184 tests |
| `uv run pytest --cov` | PASS | 87% (`fail_under` 85) |
| `uv run ruff check` | PASS | `src/`, `tests/`, `scripts/` |
| `uv run ruff format --check` | PASS | |
| `uv run ty check` | PASS | |
| `node --test tests/unit/extensions/*.mjs` | PASS | capture evidence helper |
| `uv run python -m webmedia_dl.schema_export` | PASS | 20 schemas + index |
| `uv run python scripts/validate_bundle.py` | PASS | 159 pack paths + extension/app shells |
| `uv run webmedia-dl doctor` ffmpeg | PASS | `/usr/bin/ffmpeg` |
| `uv run webmedia-dl doctor` yt-dlp / gallery-dl / magick | BLOCKED | binaries not installed |
| Apple device runtime / Xcode | BLOCKED | Linux CI; SwiftUI shells, share/intents, continuity companion present under `apps/` |
| Signing / notarization / App Review / legal | BLOCKED | `webmedia-dl doctor` |
| Browser store submission | BLOCKED | `webmedia-dl doctor` |
| Simulated `PASS` | PASS | tests reject planned/simulated PASS |
| DRM circumvention | PASS | encrypted HLS/DASH refused; clear HLS/DASH byte-range slices concatenated |
| Default telemetry | PASS | false in doctor and profiles |
| Envelope replay | PASS | consumed nonce cannot be opened twice |
| Companion native command | PASS | `/v1/companion` rejects `nativeCommand` and provider argv |
| Cooperative per-job pause checkpoint | PASS | mixed-media pause keeps registered sources; resume acquires remaining kinds |
| Pause/resume last job | PASS | CLI `--job`, `/v1/jobs/{id}/pause`, companion `pause_job`/`resume_job`, Apple shells |
| Mixed-media containment | PASS | one kind failure still publishes the other; `job.completed` records `partial`/`failed_kinds` |
| Job-scoped cancel and atomic claim | PASS | canceling one job does not poison the next; `claim_next` is compare-and-set |
| Packaged runtime assets | PASS | presets/policies/ImageMagick policy load from `webmedia_dl.runtime` without a git checkout |
| Browser one-tap token | PASS | extension storage persists the worker token after first paste |
| History schema | PASS | `HistoryEntry` JSON schema + Swift `WebMediaDLHistoryEntry` |
| DASH AdaptationSet + live poll | PASS | self-closing Representation inherits AdaptationSet BaseURL/template; dynamic MPD/HLS polls new segments |
| Typed event payloads | PASS | `EventRecord` rejects stdout/stderr/argv/nativeCommand/cookie paths |
| Files/clipboard/PhotoKit contracts | PASS | security-scoped path boundary; clipboard URL is never `local_path`; PhotoKit write stays closed |
| Wheel install | PASS | isolated `uv` venv import of packaged `runtime/export-presets.json` and `webmedia-dl --help` |
| Original planning-pack ZIP byte compare | BLOCKED | zip not in this workspace; 156 overlay files reconstructed |

Planning overlay files reconstructed from the 2026-08-18 pack inventory except
`START_HERE.md`, `product-brief.md`, and `system-architecture.md`, which were
recovered byte-for-byte from a prior cloud-agent transcript.
