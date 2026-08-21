# Validation report

| Gate | Status | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 416 tests |
| `uv run pytest --cov` | PASS | 99.28% (`fail_under` 85) |
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
| Queue durability | PASS | legacy `job_context` columns migrate; `claim_next` CAS misses return none; invalid JSON checkpoints become `{}`; `next_runnable` ignores non-accepted jobs |
| Publication skip | PASS | preview-only produced sets and `include_original=false` leave no publishable artifacts; validation failures fail the job |
| Worker API errors | PASS | unknown pairing confirm/submit/plan/envelope fail closed; companion envelope non-objects are 400; loopback `serve` reaches uvicorn; `GET /v1/jobs` lists history; plan uses pairing id from auth headers; empty `run-next` returns `job: null` |
| Cancel during acquire | PASS | mixed-media HTTP cancel during the first kind raises closed to `cancelled` without publishing |
| All-kind DRM | PASS | every candidate `DrmRefused` re-raises the original error instead of a generic empty-acquisition message |
| SOURCE validation skip | PASS | a failed SOURCE validation still publishes a validated remux derivative |
| Export pause checkpoint | PASS | pause during remux planning leaves `stage=exporting` and completed keep-original ops |
| Already-acquired kind skip | PASS | resume with `acquired_kinds=["image"]` fetches remaining video only |
| Duplicate failed-kind | PASS | a kind already recorded in the checkpoint is not appended twice |
| DERIVATIVE validation skip | PASS | a failed remux validation still publishes the original SOURCE |
| Optional dependent skip | PASS | an optional op whose required input failed is skipped without failing the plan |
| Artifact store 100% | PASS | dest-exists skip, sha mismatch, empty provenance merge, occurrences-only seed, lineage cycles |
| DASH video/audio split | PASS | `record_kind_streams` writes separate VIDEO and AUDIO artifacts; `_period_parts` prefers video |
| Live poll stop + audio 400 | PASS | `should_stop` after the first live round raises without refetch; HLS audio playlist HTTP 400 fails closed |
| HTML gallery/embed | PASS | picture/srcset, embed/object, AMP media, JSON-LD URL lists, javascript: skip, three-image gallery |
| CLI/schema `__main__` | PASS | `webmedia-dl alias-note` via `run_path` and `python -m webmedia_dl.schema_export` |
| Queue-paused resume | PASS | `resume_job` returns `accepted` and does not execute while the queue is paused |
| Empty output_paths fallback | PASS | provider result with no `output_paths` still registers `output_path` |
| Photos/staging publication | PASS | Photos destination raises; staging-only returns source paths; missing approved path fails closed |
| Probe timeout/encrypted tags | PASS | ffprobe timeout returns none; `ENCRYPTED=yes` tags mark the stream encrypted |
| Empty srcset skip | PASS | blank HTML `srcset` tokens are skipped instead of crashing discovery |
| ffmpeg `%(ext)s` stem | PASS | `clip.%(ext)s` matches `clip.mkv` among other created files |
| Cookie ledger JSON | PASS | non-list store, non-dict/incomplete grants, unknown grant ids, deny-name advisory, save without lock handle, and unresolved `resolve_cookie_path` fail closed |
| Probe encrypted field | PASS | stream `encrypted: true` is recorded; non-dict tags are not treated as encrypted |
| Probe unavailable | PASS | `probe_media` none records `probe-available:BLOCKED` and still publishes identity-validated sources |
| Resume missing sources | PASS | acquired kinds with unrestored `source_ids` fail closed instead of a silent empty publish |
| Packaging directories | PASS | extension zip `rglob` skips directories and includes nested files |
| URL never a path | PASS | URL intake with `local_path` or `file:` normalized_url raises; extra provider argv is refused |
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
