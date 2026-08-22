# Validation report

| Gate | Status | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 605 tests locally; GitHub Actions `ci` run `32574304361` (`c255db7`) passed Python (602 pytest, 100%), doctor probes, and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED), including PATH-isolated wheel doctor BLOCKED status. `32574079043` (`2628c2f`) passed Python (602 pytest, 100%) with yt-dlp / gallery-dl / ffmpeg doctor PASS. `32573782710` (`2ee51ec`) passed Python (600 pytest, 100%) after fail-closing container preference. `32572904900` (`7981aaa`) passed Python (583 pytest, 100%) and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED). `32572653043` (`0f40550`) recorded `32572254327` compile evidence; `32572254327` (`2e5cd5b`) kept publishable history and job inspect ids; `32571904208` (`d5fee40`) merged provenance and publishable job-detail ids; `32569815075` (`91eeb25`) decoded plan JSON objects; `32569700666` (`ae33eda`) passed Python and failed Swift plan-body slash escaping; `32569147243` (`5932ebc`) passed Python and Swift after speaking App Intent results. `32568400311` (`b2839e6`) hopped complete-client queue buttons onto Core; `32568126057` (`f474719`) boxed Mac worker spawn; `32567922144` (`6516591`) passed Python and failed Swift 6 non-Sendable start closures; `32567533760` (`6aad227`) passed Python and failed Swift 6 Mac `WebMediaDLMacWorkerLaunch` Sendable |
| `uv run pytest --cov` | PASS | 605 tests at 100% locally (`fail_under` 100); GitHub `32574824967` (`810237b`) was 604 tests at 100% |
| `uv run ruff check` | PASS | `src/`, `tests/`, `scripts/` |
| `uv run ruff format --check` | PASS | |
| `uv run ty check` | PASS | |
| `node --test tests/unit/extensions/*.mjs` | PASS | 7 tests including popup `#send` → loopback POST |
| `uv run python -m webmedia_dl.schema_export` | PASS | 19 schemas + index |
| `uv run python scripts/validate_bundle.py` | PASS | 159 pack paths + extension/app shells + links + task DAG + traceability + archive safety + clean extraction |
| `uv run webmedia-dl doctor` ffmpeg | PASS | `/usr/bin/ffmpeg -version` executed PASS |
| `uv run webmedia-dl doctor` ffprobe | PASS | `tools.ffprobe` version probe executed PASS on this host |
| `uv run webmedia-dl doctor` ImageMagick | WARN | IM6 `convert -version` executed; `magick` is absent |
| ImageMagick convert pipeline | PASS | `test_pipeline_executes_imagemagick_convert` runs `process.imagemagick.convert` on a PNG |
| Stream-copy semantic parity | PASS | remux/copy derivatives must keep source codecs and duration; missing probes stay BLOCKED; lossy transcode skips `semantic-parity` |
| Complete-client share http-direct | PASS | iPhone/iPad/visionOS share adapters and App Intents call `saveIfDirect` then restore the App Group Files bookmark via `WebMediaDLShareIntake.fromSavedBookmark`; Mac share/intents stay worker-only; watch/tv still lack `WebMediaDLHttpDirect` |
| Queue pause durability | PASS | a second `Pipeline` on the same data dir observes the SQL pause flag and does not `run_next` until resume |
| Extension collector under pytest | PASS | `test_extension_collector_returns_no_native_command` runs `node --test tests/unit/extensions/capture.test.mjs` |
| `uv run webmedia-dl doctor` yt-dlp / gallery-dl | PASS | GitHub `32574079043` (`2628c2f`) executed `webmedia-dl doctor`; yt-dlp, gallery-dl, and ffmpeg version probes were PASS. `yt-dlp` and `gallery-dl` are in the `dev` group only. An isolated wheel install reports those CLIs BLOCKED and does not download them |
| Apple device runtime / Xcode | BLOCKED | Device UI, PhotoKit writes, signing, and store submission stay BLOCKED; GitHub `macos-15` compiles Apple packages |
| Signing / notarization / App Review / legal | BLOCKED | `webmedia-dl doctor` |
| Browser store submission | BLOCKED | `webmedia-dl doctor` |
| Simulated `PASS` | PASS | tests reject planned/simulated PASS |
| DRM circumvention | PASS | encrypted HLS/DASH refused before any segment fetch; `#EXT-X-SESSION-KEY` SAMPLE-AES/FairPlay refused before fetch; `cenc` / Widevine / PlayReady UUIDs / `skd://` detected; mixed clear-then-key records the prefix only; later live-poll DRM stops without fetching protected parts; dynamic A/V DASH stops remaining renditions after late ContentProtection; growing HLS byte-ranges refetch and append only the new suffix; a later growing-range HTTP error fails closed; already-written live ranges are not rewound; HTTP probe encryption quarantines and does not fall back to yt-dlp; a later `_record_probe` that reports encryption after a clear acquire probe fails closed without quarantining |
| Pairing profile bound | PASS | restricted/browser/watch/tv pairing stays on the client profile; unknown/full/expired pairing and missing/mismatched session keys fail closed; CLI `pair create/confirm` reports `DelegationDenied` |
| Cookie grants | PASS | job-bound grants persist in `cookie-grants.json` with merge/`0600` lock; dump-json uses the grant; relative and in-repo paths rejected; HTML replacement, missing files, unresolved paths, and path changes after issue are refused; `run_next` restores the grant from job context and passes `--cookies` |
| Default telemetry | PASS | false in doctor and profiles; `policy-profiles.json` cannot enable DRM circumvention, telemetry, cookie widening, subprocess, or delegation |
| Publish sibling isolation | PASS | a failed validation or unreadable sibling does not abort other validated destination copies; a failed remux or export policy error still publishes the original source |
| Packaged runtime fallback | PASS | `runtime_root` / `runtime_file` fall back to checkout `resources/` without a packaged `runtime/` tree; `repo_root` fails closed when `pyproject.toml` is absent |
| CLI paste/speak/drop fail-closed | PASS | DRM locators exit 1 with `job.error`; missing drop files fail closed; drop publication errors exit 1 |
| Fetch bounds | PASS | HTML truncate, media overflow error, streaming within-limit, redirect bound, owned client closed |
| Queue durability | PASS | legacy `job_context` columns migrate; `claim_next`/`claim` CAS misses return none; `UPDATE … RETURNING` plus `BEGIN IMMEDIATE` keeps concurrent claims exclusive; `submit` claims inside `_run`; `set_state` reads pause/cancel flags without re-parsing evidence; pause/cancel after `publishing` fail closed and publication stays `completed`; invalid JSON checkpoints become `{}`; malformed browser evidence fails the job; `next_runnable` ignores non-accepted jobs |
| Source artifact identity | PASS | SOURCE `artifact_id` must be `sha256:<digest>`; titles and `plan:source` sentinels are rejected |
| Capability health probe | PASS | present binaries whose version probe fails are `unhealthy`; missing binaries stay `missing`; a resolved path that does not exist is `missing`; `/bin/false` is not `healthy`; `http-direct` records an executed httpx probe; `validate.container` is not `healthy` when ffprobe is missing |
| Extension popup one-tap | PASS | `popup.js` `#send` click collects page URLs and POSTs `/v1/jobs` with no `nativeCommand` |
| Complete-client Mac relay | PASS | iPhone/iPad/visionOS heavy submit, history, queue controls, last-job JSON inspect, **Explain plan** (`POST /v1/plan`), and **Worker doctor** (`GET /v1/doctor`) use a saved private/loopback Mac URL plus pairing and do not copy the Mac worker bearer. Siri/Shortcuts speak the worker or relay response. `WebMediaDLCompleteClientControl` refuses unknown kinds, cancel/job-detail without a job UUID, and missing pairing before any POST; history returns a spoken job list instead of `"ok"`. Plan/doctor without a saved relay raise `pairingRequired`. Mac `WebMediaDLMacRelayServer` listens on private/loopback HTTP, `forwardToLoopback` rewrites to `127.0.0.1`, strips `Authorization` / `X-WebMedia-Token`, injects the Mac loopback bearer only for `/v1/companion` after pairing headers, and refuses `/v1/pair/confirm`. Public peers / `nativeCommand` are refused. Companion pairing headers must be a confirmed pairing even with the Mac bearer. Relay paste URLs are `http` private LAN, `.local`, or loopback; HTTPS and extra-label hosts are refused. iPhone WatchConnectivity forwards watch companion messages to that Mac relay; tvOS uses LAN companion transport, not WCSession. Complete-client file drops POST `/v1/staging` with a sha256 digest and submit the Mac staging path (`staging_only`); a phone sandbox path is not queued. Complete-client URL jobs with a Files bookmark also submit `staging_only`; `GET /v1/artifacts/{id}/content` pulls published bytes into the local Files bookmark. JSON relay stays 1 MiB; staging uses a separate byte bound. GitHub `macos-15` run `32574824967` on `810237b` executed Core `swift test` 18 tests, 0 failures; 12× BUILD SUCCEEDED. Physical device radio remains BLOCKED |
| Artifact content pull | PASS | `GET /v1/artifacts/{id}/content` streams SOURCE/DERIVATIVE bytes with `X-WebMedia-Digest`; quarantine roles and paths outside the store fail closed |
| Mac worker supervision | PASS | Mac app calls `WebMediaDLMacWorkerProcess.start` (`webmedia-dl serve --host 127.0.0.1 --port 8765`); `startOrClaimExisting` takes a `@Sendable` start that returns `WebMediaDLUncheckedBox<AnyObject>` and a `@unchecked Sendable` `WebMediaDLMacWorkerLaunch` so Swift 6 can receive spawn/claim in a nonisolated `Task`; UI updates use `MainActor.run`; spawn failure probes unauthenticated `GET /health` before claiming an existing worker; `homeDirectoryForCurrentUser` is `#if os(macOS)` so complete-client SDKs compile; complete clients never spawn `Process` |
| Publication skip | PASS | preview-only produced sets and `include_original=false` leave no publishable artifacts; a restored preview plus source skips the preview at validation and publishes the source; validation failures fail the job |
| Worker API errors | PASS | unknown pairing confirm/submit/plan/envelope fail closed; companion envelope non-objects are 400; pair `personal-full`/unknown profiles are 400; companion unknown job ids are 404; sealed companion `nativeCommand` is 400 then nonce-replay fails; loopback `serve` reaches uvicorn; `serve_worker` refuses `0.0.0.0`; `GET /v1/jobs` lists history; plan uses pairing id from auth headers; empty `run-next` returns `job: null`; `/v1/plan` DRM locators are 400 with no provider execution or job creation; `/v1/jobs` destinations outside `approved_roots` fail the job with `job.failed` |
| Cancel during acquire | PASS | mixed-media HTTP cancel during the first kind raises closed to `cancelled` without publishing |
| All-kind DRM | PASS | every candidate `DrmRefused` re-raises the original error instead of a generic empty-acquisition message |
| SOURCE validation skip | PASS | a failed SOURCE validation still publishes a validated remux derivative |
| Export pause checkpoint | PASS | pause during remux planning leaves `stage=exporting` and completed keep-original ops |
| Already-acquired kind skip | PASS | resume with `acquired_kinds=["image"]` fetches remaining video only |
| Duplicate failed-kind | PASS | a kind already recorded in the checkpoint is not appended twice |
| DERIVATIVE validation skip | PASS | a failed remux validation still publishes the original SOURCE |
| Optional dependent skip | PASS | an optional op whose required input failed is skipped without failing the plan |
| Artifact store 100% | PASS | dest-exists skip, sha mismatch, empty provenance merge, occurrences-only seed, lineage cycles; same-digest DERIVATIVE then SOURCE keeps parent ids and occurrences while promoting to immutable SOURCE |
| DASH video/audio split | PASS | `record_kind_streams` writes separate VIDEO and AUDIO artifacts; `_period_parts` prefers video |
| Live poll stop + audio 400 | PASS | `should_stop` after the first live round raises without refetch; HLS audio playlist HTTP 400 fails closed |
| HTML gallery/embed | PASS | picture/srcset, embed/object, AMP media, JSON-LD URL lists, javascript: skip, three-image gallery |
| CLI/schema `__main__` | PASS | `webmedia-dl alias-note` via `run_path` and `python -m webmedia_dl.schema_export` |
| Queue-paused resume | PASS | `resume_job` returns `accepted` and does not execute while the queue is paused |
| Empty output_paths fallback | PASS | provider result with no `output_paths` still registers `output_path`; existing `output_paths` still register when the primary `output_path` is missing; exit 0 with no files is `produced no source files` |
| Photos/staging publication | PASS | Photos destination raises; staging-only returns source paths; missing approved path fails closed |
| Probe timeout/encrypted tags | PASS | ffprobe timeout returns none; `ENCRYPTED=yes` tags mark the stream encrypted |
| Empty srcset skip | PASS | blank HTML `srcset` tokens are skipped instead of crashing discovery |
| ffmpeg `%(ext)s` stem | PASS | `clip.%(ext)s` matches `clip.mkv` among other created files |
| Cookie ledger JSON | PASS | non-list store, non-dict/incomplete grants, unknown grant ids, malformed job ids, save without lock handle, and unresolved `resolve_cookie_path` fail closed |
| Probe encrypted field | PASS | stream `encrypted: true` is recorded; non-dict tags are not treated as encrypted |
| Probe unavailable | PASS | `probe_media` none records `probe-available:BLOCKED` and still publishes identity-validated sources |
| Resume missing sources | PASS | acquired kinds with unrestored `source_ids` fail closed instead of a silent empty publish; acquired-kinds with empty `source_ids` raise `no source artifact` |
| Packaging directories | PASS | extension zip `rglob` skips directories and includes nested files |
| Leftover DASH media | PASS | `media=` outside SegmentTemplate is recorded; duplicate leftover URLs are skipped |
| Supplied live parts | PASS | explicit HLS parts are written; AES-128 inspect still refuses before fetch |
| Exporting resume | PASS | `stage=exporting` with restored `produced_ids` completes without empty-source fill |
| Discovery HTML 100% | PASS | empty srcset/poster, meta without content, picture source without MIME, track preload, NDJSON blank lines |
| Forbidden export loss | PASS | `plan_export` refuses `LossClass.FORBIDDEN` before returning a plan |
| SegmentTimeline clock | PASS | `S` without `t` keeps the running `$Time$` clock |
| Extra-args validator | PASS | `AcquisitionStrategy.forbid_user_argv` rejects non-empty extra argv |
| TimeoutExpired cancel/pause | PASS | `_tracked_run` terminate-and-return 130/143 when cancel or pause is set during communicate timeout |
| Export progress null/duplicate | PASS | `on_progress` accepts a null artifact and does not double-append a completed operation key |
| Duplicate exported ids | PASS | `stage=exported` with duplicate `produced_ids` still completes |
| Acquired remote skip | PASS | resume at `stage=acquired` does not refetch remote media |
| ImageMagick convert alias | PASS | health and argv resolve IM6 `convert` when `magick` is missing |
| Job-detail / run-next helpers | PASS | `artifact_ids` come from `JOB_COMPLETED` publishable ids on job detail, history, and `webmedia-dl job`; empty queue returns `job: null`; a queued job returns events |
| Swift Core CI job | PASS | GitHub Actions `ci` run `32572904900` on `7981aaa`: `IdentityTests` executed 6 tests, 0 failures on `macos-15` |
| Swift Core contract tests | PASS | `ContractTests.swift` executed 12 tests, 0 failures with IdentityTests (6) on GitHub `macos-15` run `32572904900` (`7981aaa`) |
| Apple package compile CI | PASS | GitHub Actions `ci` run `32574304361` on `c255db7`: Core `swift test` 18 tests, 0 failures (`ContractTests` 12 + `IdentityTests` 6); Safari handler `swiftc -typecheck`; 8× package `BUILD SUCCEEDED` plus 4× unsigned `com.apple.product-type.app-extension` `.appex`. Device runtime stays BLOCKED |
| OpenSpec scenarios | PASS | every capability spec scenario has WHEN/THEN; each scenario title maps to a named Python or Swift test in a pinned source file; popup markup is parsed; drop records `local_path`; local submit does not upload; job submit forbids native argv; queue-level events use a zero UUID; `wmdl` is not the console script; remux precedes transcode; failed derivatives do not block siblings; `run_next` restores cookie grants, HTML, and browser evidence; unsafe format ids are refused; doctor keeps signing/stores/legal BLOCKED |
| Builtin manifests / profiles | PASS | every shipped provider sets `install_automatic` false and `accepts_user_argv` false; every shipped profile forbids telemetry, DRM circumvention, and delegation |
| Graph relation schema | PASS | Swift `WebMediaDLGraphRelation` raw values match `GraphEdge.relation` |
| Live DRM inspect skip | PASS | `recordable_parts` always refuses session keys and DASH UUID/cenc signals; there is no inspect=False DRM bypass |
| WatchConnectivity class headers | PASS | WCSessionDelegate is an extension; class signatures are not split across `#else` |
| URL never a path | PASS | URL intake with `local_path` or `file:` normalized_url raises; extra provider argv is refused |
| Live aggregate bound + kinds | PASS | cumulative byte budget; separate VIDEO/AUDIO artifacts; audio-only DASH uses the highest-bandwidth audio Representation; SegmentBase ranges including mediaRange; multi-period occurrences; empty recordings and HTTP 400 playlists fail closed; nested/audio `should_stop` aborts before further fetches |
| DASH AdaptationSet + live poll | PASS | self-closing Representation inherits AdaptationSet BaseURL/template; dynamic MPD/HLS polls new segments; later ContentProtection/AES-128 stops without fetching protected parts; `startNumber` and `$$` template tokens expand without a phantom `$Number=1` segment; `$Number$` without SegmentTimeline expands through `endNumber` or Period/`mediaPresentationDuration` (capped at 64) |
| Container gate | PASS | ffprobe evidence required; filename suffix cannot PASS; `BLOCKED`/empty evidence cannot publish. Python and Swift `ExportIntent` refuse hostile `container_preference` values |
| Wheel package-extensions | PASS | isolated wheel install writes six extension archives from packaged runtime trees |
| Envelope replay | PASS | consumed nonce cannot be opened twice; rows older than 24h are pruned; malformed envelopes and tampered MAC fail closed; non-hex session keys still round-trip |
| Companion native command | PASS | `/v1/companion` rejects `nativeCommand` and provider argv; extra JSON is 422; sealed cancel/pause_job/resume_job require a job UUID |
| Cooperative per-job pause checkpoint | PASS | mixed-media pause keeps registered sources; resume acquires remaining kinds |
| Publication I/O | PASS | `publish_artifacts` `OSError` becomes `PublicationError`; the durable job is `failed` with `job.failed` |
| CLI unknown controls | PASS | unknown `job`/`cancel`/`pause`/`resume`/companion ids and DRM `plan` exit 1 with user-facing text |
| Unconfirmed pairing | PASS | iOS jobs with an unconfirmed pairing id raise `DelegationDenied` and do not execute yt-dlp |
| Confirmed pairing Mac execution | PASS | confirmed pairing keeps `policy_profile_id=personal-restricted`, sets `worker_id` to the Mac host, and runs yt-dlp; `require_pass` demands executed hash-match and size-match; hop-by-hop fetch refuses `file:`/`http:` redirects; pair/control JSON forbids extras and `nativeCommand`. Proven on GitHub Actions `ci` run `32555270688` (`89f7492`) |
| Mixed-media containment | PASS | one kind failure still publishes the other; `job.completed` records `partial`/`failed_kinds` |
| Job-scoped cancel and atomic claim | PASS | canceling one job does not poison the next; `claim_next` is compare-and-set |
| Packaged runtime assets | PASS | presets/policies/ImageMagick policy load from `webmedia_dl.runtime` without a git checkout |
| Browser one-tap token | PASS | extension storage persists the worker token after first paste |
| History schema | PASS | `HistoryEntry` JSON schema + Swift `WebMediaDLHistoryEntry` decoded on all six surfaces |
| DASH AdaptationSet + live poll | PASS | self-closing Representation inherits AdaptationSet BaseURL/template; dynamic MPD/HLS polls new segments; later ContentProtection/AES-128 stops without fetching protected parts; `startNumber` and `$$` template tokens expand without a phantom `$Number=1` segment; `$Number$` without SegmentTimeline expands through `endNumber` or Period/`mediaPresentationDuration` (capped at 64) |
| DASH/HLS rendition selection | PASS | highest-bandwidth video Representation; audio-only picks highest audio; muxed formats prefer a combined id over `137+140` when one stream already has both codecs; HLS master follows highest BANDWIDTH |
| Multi-period DASH | PASS | each Period keeps its selected video; later Periods are concatenated, not dropped |
| Sealed companion envelope | PASS | `/v1/companion` opens AES-GCM pairing envelope once and rejects replay |
| Vision share + Files destinations | PASS | share Info.plist principals; `fileImporter` + `bookmarkData`; PhotoKit write stays closed |
| Typed event payloads | PASS | `EventRecord` rejects stdout/stderr/argv/nativeCommand/cookie paths; Swift `WebMediaDLEvent` decode/init raises on those keys |
| Files/clipboard/PhotoKit contracts | PASS | security-scoped bookmark boundary; Swift `ExportIntent` uses `allows()` so `/approved/../escape` is denied; complete clients persist Files bookmarks locally and pull published bytes; Mac submit still carries `security_scoped_bookmark`; clipboard URL is never `local_path`; PhotoKit write stays closed |
| Complete-client on-device HTTP | PASS | iPhone/iPad/visionOS `WebMediaDLHttpDirect` downloads direct HTTPS media into a Files bookmark after `mediaURL` requires a host and refuses `file`/`javascript`/`data`/`blob`/`about`/`chrome`/`chrome-extension`; cleartext `http` is parsed but not transferred on-device; cookies are disabled; redirects are capped and non-2xx (including 3xx) bodies are refused; empty roots are `filesDestinationRequired`; stale or unresolvable bookmark data is `destinationDenied`; page/live locators require pairing; DRM signals refuse before write; byte overflow refuses before write; `.`/`..` stems become `source`; `URLSession.bytes` stops at `maxBytes`; watchOS/tvOS stay capture-only |
| Share sheet extractors | PASS | HTTPS locators stay URL intake; `file://` paths use drop intake; awaited `NSItemProvider` load; complete-client drops stage onto the Mac worker before submit |
| Privacy manifests | PASS | every app and share extension ships `PrivacyInfo.xcprivacy` with `NSPrivacyAccessedAPICategoryUserDefaults` reason `1C8F.1` and tracking disabled |
| Companion Mac relay | PASS | watchOS `WCSessionDelegate` on the iPhone companion hops `userInfo` onto the main actor and forwards typed messages to the Mac LAN relay; tvOS uses `WebMediaDLLocalNetworkCompanionTransport`; the Mac app does not activate `WCSession`; `WebMediaDLMacCompanionForwarder` drains sealed/plain companion messages over LAN HTTP with the pairing session key and refuses empty envelope fields; `nativeCommand` null |
| HTTP stream stop | PASS | `bound_fetch(..., should_stop=)` aborts mid-stream; cancel discards completed HTTP fetch; pause commits |
| Wheel install | PASS | isolated `uv` venv import of packaged `runtime/export-presets.json` and `webmedia-dl --help` |
| CLI names in README | PASS | every Typer command name appears in `README.md` |
| App Group + pairing clients | PASS | `group.local.webmedia-dl` on apps and share extensions; unauthenticated loopback `POST /v1/pair` bootstrap; Mac-only confirm parses `session_key`; iPhone/iPad/vision derive SHA256(`nonce:mac-confirm`) locally and restore Files bookmarks; watch/tv `lastJobId` comes from companion history/response |
| Original planning-pack ZIP byte compare | BLOCKED | zip not in this workspace; 159 overlay files reconstructed |
| Real WatchConnectivity radio | BLOCKED | WCSession scaffolding + queued fallback; no Apple radio on Linux |
| Safari wrapping / signed NSExtension | BLOCKED | `swiftc -typecheck` of `SafariWebExtensionHandler.swift` executed on GitHub `macos-15`; the handler `try`s JSON encode, `cancelRequest`s on encode/HTTP failure, and `completeRequest`s only on 2xx; unsigned share-extension `.appex` layouts are assembled with package type `XPC!`; GitHub `32564115037` (`7b909d0`) `xcodebuild`s unsigned `com.apple.product-type.app-extension` Mach-O `.appex` products; signed Xcode NSExtension wrapping is not executed |

Planning overlay files reconstructed from the 2026-08-18 pack inventory except
`START_HERE.md`, `product-brief.md`, and `system-architecture.md`, which were
recovered byte-for-byte from a prior cloud-agent transcript.
