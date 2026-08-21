# Validation report

| Gate | Status | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 319 tests |
| `uv run pytest --cov` | PASS | 93.81% (`fail_under` 85) |
| `uv run ruff check` | PASS | `src/`, `tests/`, `scripts/` |
| `uv run ruff format --check` | PASS | |
| `uv run ty check` | PASS | |
| `node --test tests/unit/extensions/*.mjs` | PASS | 6 tests including mocked fetch submit |
| `uv run python -m webmedia_dl.schema_export` | PASS | 20 schemas + index |
| `uv run python scripts/validate_bundle.py` | PASS | 159 pack paths + extension/app shells |
| `uv run webmedia-dl doctor` ffmpeg | PASS | `/usr/bin/ffmpeg` executed PASS |
| `uv run webmedia-dl doctor` yt-dlp / gallery-dl / magick | BLOCKED | binaries not installed |
| Apple device runtime / Xcode | BLOCKED | Linux CI; Swift source contracts under `apps/` are not compiled here |
| Signing / notarization / App Review / legal | BLOCKED | `webmedia-dl doctor` |
| Browser store submission | BLOCKED | `webmedia-dl doctor` |
| Simulated `PASS` | PASS | tests reject planned/simulated PASS |
| DRM circumvention | PASS | encrypted HLS/DASH refused before any segment fetch; mixed clear-then-key records the prefix only; later live-poll DRM stops without fetching protected parts |
| Pairing profile bound | PASS | restricted/browser/watch/tv pairing stays on the client profile; unknown/full/expired pairing and missing/mismatched session keys fail closed; CLI `pair create/confirm` reports `DelegationDenied` |
| Cookie grants | PASS | job-bound grants persist in `cookie-grants.json` with merge/`0600` lock; dump-json uses the grant; relative and in-repo paths rejected |
| Default telemetry | PASS | false in doctor and profiles; `policy-profiles.json` cannot enable DRM circumvention, telemetry, cookie widening, subprocess, or delegation |
| Publish sibling isolation | PASS | a failed validation or unreadable sibling does not abort other validated destination copies; a failed remux or export policy error still publishes the original source |
| Packaged runtime fallback | PASS | `runtime_root` / `runtime_file` fall back to checkout `resources/` without a packaged `runtime/` tree; `repo_root` fails closed when `pyproject.toml` is absent |
| CLI paste/speak/drop fail-closed | PASS | DRM locators exit 1 with `job.error`; missing drop files fail closed; drop publication errors exit 1 |
| Fetch bounds | PASS | HTML truncate, media overflow error, streaming within-limit, redirect bound, owned client closed |
| Live aggregate bound + kinds | PASS | cumulative byte budget; separate VIDEO/AUDIO artifacts; audio-only DASH uses the highest-bandwidth audio Representation; SegmentBase ranges including mediaRange; multi-period occurrences; empty recordings and HTTP 400 playlists fail closed; nested/audio `should_stop` aborts before further fetches |
| DASH AdaptationSet + live poll | PASS | self-closing Representation inherits AdaptationSet BaseURL/template; dynamic MPD/HLS polls new segments; later ContentProtection/AES-128 stops without fetching protected parts; `startNumber` and `$$` template tokens expand without a phantom `$Number=1` segment |
| Container gate | PASS | ffprobe evidence required; filename suffix cannot PASS; `BLOCKED`/empty evidence cannot publish |
| Wheel package-extensions | PASS | isolated wheel install writes six extension archives from packaged runtime trees |
| Envelope replay | PASS | consumed nonce cannot be opened twice; malformed envelopes and tampered MAC fail closed; non-hex session keys still round-trip |
| Companion native command | PASS | `/v1/companion` rejects `nativeCommand` and provider argv |
| Cooperative per-job pause checkpoint | PASS | mixed-media pause keeps registered sources; resume acquires remaining kinds |
| Pause/resume last job | PASS | CLI `--job`, `/v1/jobs/{id}/pause`, companion `pause_job`/`resume_job`, Apple shells |
| Mixed-media containment | PASS | one kind failure still publishes the other; `job.completed` records `partial`/`failed_kinds` |
| Job-scoped cancel and atomic claim | PASS | canceling one job does not poison the next; `claim_next` is compare-and-set |
| Packaged runtime assets | PASS | presets/policies/ImageMagick policy load from `webmedia_dl.runtime` without a git checkout |
| Browser one-tap token | PASS | extension storage persists the worker token after first paste |
| History schema | PASS | `HistoryEntry` JSON schema + Swift `WebMediaDLHistoryEntry` decoded on all six surfaces |
| DASH AdaptationSet + live poll | PASS | self-closing Representation inherits AdaptationSet BaseURL/template; dynamic MPD/HLS polls new segments; later ContentProtection/AES-128 stops without fetching protected parts; `startNumber` and `$$` template tokens expand without a phantom `$Number=1` segment |
| DASH/HLS rendition selection | PASS | highest-bandwidth video Representation; audio-only picks highest audio; muxed formats prefer a combined id over `137+140` when one stream already has both codecs; HLS master follows highest BANDWIDTH |
| Multi-period DASH | PASS | each Period keeps its selected video; later Periods are concatenated, not dropped |
| Sealed companion envelope | PASS | `/v1/companion` opens AES-GCM pairing envelope once and rejects replay |
| Vision share + Files destinations | PASS | share Info.plist principals; `fileImporter` + `bookmarkData`; PhotoKit write stays closed |
| Typed event payloads | PASS | `EventRecord` rejects stdout/stderr/argv/nativeCommand/cookie paths |
| Files/clipboard/PhotoKit contracts | PASS | security-scoped bookmark boundary; complete clients persist and submit `security_scoped_bookmark`; clipboard URL is never `local_path`; PhotoKit write stays closed |
| Share sheet extractors | PASS | HTTPS locators stay URL intake; `file://` paths use drop intake; awaited `NSItemProvider` load |
| Companion Mac relay | PASS | watchOS/tvOS `WCSessionDelegate` activate + `transferUserInfo`; Mac `forwardSealed` with pairing session key; `nativeCommand` null |
| HTTP stream stop | PASS | `bound_fetch(..., should_stop=)` aborts mid-stream; cancel discards completed HTTP fetch; pause commits |
| Wheel install | PASS | isolated `uv` venv import of packaged `runtime/export-presets.json` and `webmedia-dl --help` |
| CLI names in README | PASS | every Typer command name appears in `README.md` |
| App Group + pairing clients | PASS | `group.local.webmedia-dl` on apps and share extensions; unauthenticated loopback `POST /v1/pair` bootstrap; Mac-only confirm parses `session_key`; iPhone/iPad/vision derive SHA256(`nonce:mac-confirm`) locally and restore Files bookmarks; watch/tv `lastJobId` comes from companion history/response |
| Original planning-pack ZIP byte compare | BLOCKED | zip not in this workspace; 156 overlay files reconstructed |
| Real WatchConnectivity radio | BLOCKED | WCSession scaffolding + queued fallback; no Apple radio on Linux |
| Safari wrapping / signed NSExtension | BLOCKED | source handler conforms to `NSExtensionRequestHandling`; Xcode wrapping is not executed |

Planning overlay files reconstructed from the 2026-08-18 pack inventory except
`START_HERE.md`, `product-brief.md`, and `system-architecture.md`, which were
recovered byte-for-byte from a prior cloud-agent transcript.
