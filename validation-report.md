# Validation report

| Gate | Status | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 103 tests |
| `uv run pytest --cov` | PASS | 88% (`fail_under` 85) |
| `uv run ruff check` | PASS | `src/`, `tests/`, `scripts/` |
| `uv run ruff format --check` | PASS | |
| `uv run ty check` | PASS | |
| `node --test tests/unit/extensions/*.mjs` | PASS | capture evidence helper |
| `uv run python -m webmedia_dl.schema_export` | PASS | 17 schemas + index |
| `uv run python scripts/validate_bundle.py` | PASS | 159 pack paths + extension/app shells |
| `uv run webmedia-dl doctor` ffmpeg | PASS | `/usr/bin/ffmpeg` |
| `uv run webmedia-dl doctor` yt-dlp / gallery-dl / magick | BLOCKED | binaries not installed |
| Apple device runtime / Xcode | BLOCKED | Linux CI; SwiftUI shells, share/intents, continuity bridge present under `apps/` |
| Signing / notarization / App Review / legal | BLOCKED | `webmedia-dl doctor` |
| Browser store submission | BLOCKED | `webmedia-dl doctor` |
| Simulated `PASS` | PASS | tests reject planned/simulated PASS |
| DRM circumvention | PASS | encrypted HLS/DASH refused; clear segments concatenated |
| Default telemetry | PASS | false in doctor and profiles |
| Envelope replay | PASS | consumed nonce cannot be opened twice |
| Original planning-pack ZIP byte compare | BLOCKED | zip not in this workspace; 156 overlay files reconstructed |

Planning overlay files reconstructed from the 2026-08-18 pack inventory except
`START_HERE.md`, `product-brief.md`, and `system-architecture.md`, which were
recovered byte-for-byte from a prior cloud-agent transcript.
