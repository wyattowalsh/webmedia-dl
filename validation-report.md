# Validation report

| Gate | Status | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 53 tests |
| `uv run ruff check` | PASS | src/tests/scripts |
| `uv run ty check` | PASS | |
| `node --test tests/unit/extensions/*.mjs` | PASS | capture evidence helper |
| `python scripts/validate_bundle.py` | PASS | overlay + schemas |
| Apple devices / signing / stores / App Review / legal | BLOCKED | `webmedia-dl doctor` |
| Optional provider binaries (yt-dlp, gallery-dl, magick) | BLOCKED | not installed in this environment |
| ffmpeg | PASS | `/usr/bin/ffmpeg` present |
| Simulated PASS | PASS | tests reject it |
| DRM circumvention | PASS | encrypted manifests refused |
| Default telemetry | PASS | false in doctor and profiles |

Planning overlay files reconstructed from the 2026-08-18 pack inventory except
`START_HERE.md`, `product-brief.md`, and `system-architecture.md`, which were
recovered byte-for-byte from a prior cloud-agent transcript.
