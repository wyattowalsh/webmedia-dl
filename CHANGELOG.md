# Changelog

## 0.1.0

- Plan `live.record_clear_manifest` for every `live_stream` candidate, including
  MIME-typed HLS/DASH locators without `.m3u8` / `.mpd`. Those URLs were falling
  through to yt-dlp (or no strategy) instead of the clear recorder, and capture
  labelled `mpegurl` / `dash+xml` as `video` so browser evidence could hide the
  live kind. GitHub Actions `32583436133` on `66fff1f` passed Python (624
  pytest, 100%), doctor provider probes, and Swift (18 tests, 0 failures; 12×
  BUILD SUCCEEDED) after decoding HTML-escaped JSON-LD.
- Decode HTML entities in JSON-LD script bodies after comment/CDATA unwrap
  so CMS-escaped `&quot;contentUrl&quot;` locators are collected. GitHub
  Actions `32583153141` on `969b440` passed Python (624 pytest, 100%),
  doctor provider probes, and Swift (18 tests, 0 failures; 12× BUILD
  SUCCEEDED) after unwrapping JSON-LD `CDATA` scripts.
- Unwrap JSON-LD `<![CDATA[...]]>` script bodies in the worker and browser
  capture so `contentUrl` locators are not dropped as a page-without-direct-media
  candidate. GitHub Actions `32582853577` on `88c319c` passed Python
  (624 pytest, 100%), doctor provider probes, and Swift (18 tests, 0 failures;
  12× BUILD SUCCEEDED) after binding DASH `CDATA` BaseURL values.
- Bind DASH `BaseURL` values wrapped in `CDATA` and unescape XML entities in
  DASH attributes so templates join the CDN base, not the MPD origin.
  GitHub Actions `32582502768` on `c7bdfce` passed Python (624 pytest, 100%),
  doctor provider probes, and Swift (18 tests, 0 failures; 12× BUILD
  SUCCEEDED) after refusing `data:` / `file:/` locators that lack `://`.
- Parse locator schemes with `urlparse` so `data:` and `file:/` (no `://`)
  cannot masquerade as relative HTML/JSON-LD/browser-evidence URLs.
  Capture skips the same blocked schemes. GitHub Actions `32581963314` on
  `9b29491` passed Python (624 pytest, 100%), doctor provider probes, and
  Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after joining relative
  HLS names that start with `http`.
- Join live segment URIs with `urljoin` so a relative `http-seg.ts` is not
  treated as an absolute URL. `startswith("http")` stole those names from
  the playlist base.
- GitHub Actions `32581604639` on `000f55c` passed Python (624 pytest, 100%),
  doctor provider probes, and Swift (18 tests, 0 failures; 12× BUILD
  SUCCEEDED) after collecting JSON-LD scripts that declare a charset.
- Unwrap HTML comments around JSON-LD script bodies and collect
  `link` HLS/DASH MIME types (`mpegurl` / `dash+xml`, including charset
  parameters) as live locators. Capture does the same for comments and
  alternate manifest links.
- Collect JSON-LD from `application/ld+json` scripts that carry a charset
  (or other type parameter). The old quoted-type regex required the quote
  immediately after `json` and dropped those locators.
- GitHub Actions `32581097802` on `203338e` passed Python (624 pytest, 100%),
  doctor provider probes, and Swift (18 tests, 0 failures; 12× BUILD
  SUCCEEDED) after picking HLS master variants from `BANDWIDTH` rather than
  `AVERAGE-BANDWIDTH`.
- Prefer URL-derived kinds over browser-evidence hints so a `<video><source>`
  capture labelled `image` cannot hide the mp4. Keep both JSON-LD `contentUrl`
  and `embedUrl`. HTML `<source>` inside `video`/`audio` keeps that kind even
  without a media extension. Browser capture classifies `source` from its
  parent, collects `amp-img` / `data-src`, and reads `twitter:player`.
- Pick HLS master variants from the `BANDWIDTH` attribute map, not a greedy
  `\bBANDWIDTH=` regex. `AVERAGE-BANDWIDTH` (and duplicate / non-numeric
  `BANDWIDTH`) must not steal the highest-peak media playlist.
- Collect JSON-LD `contentUrl` / `embedUrl` objects that carry `@id` or
  `url`, in the worker and in browser capture, so typed JSON-LD locators
  are not dropped as a page-without-direct-media candidate.
- Attach page-level DRM signals to browser-evidence seeds. Those URLs
  were marked `seen` before HTML/JSON-LD union, so a Widevine/`cenc`
  page could keep a clear capture candidate.
- Keep page-level `cenc`/`cbcs` DRM signals on HTML/JSON-LD candidates
  instead of re-scanning regex pattern strings (which dropped those
  hits). Parse namespace-prefixed DASH (`dash:MPD`) the same as bare
  `MPD` so ContentProtection still refuses and SegmentList ranges still
  slice. Restore the Swift `hlsKeyIsProtected` loop binding so Core
  compiles. Swift `METHOD=NONE` with a `URI` (including a quoted
  `METHOD=` query) refuses the same as Python `UNKNOWN`.
- Parse HLS `#EXT-X-KEY` / `#EXT-X-SESSION-KEY` `METHOD` from tag attributes
  so a `METHOD=` token inside a quoted `URI` cannot masquerade as `NONE`
  and fetch encrypted segments. Duplicate `METHOD` attributes and
  `METHOD=NONE` combined with `URI`/`KEYFORMAT` refuse closed. `#EXT-X-MAP`
  is parsed only as a tag (not a substring) using the same attribute map.
  HLS playlists that carry Widevine / FairPlay / `skd://` signals refuse
  closed even without a key line. Mixed clear-then-AES-128 still records
  the clear prefix only.
- Close remaining Linux-provable OpenSpec gaps: DASH `SegmentList` ranges
  against a Representation `BaseURL` are sliced instead of emitting the
  whole object; live HLS polls record a reused segment URI when
  `#EXT-X-MEDIA-SEQUENCE` advances; JSON-LD and yt-dlp dumps keep page/item
  DRM signals; mixed-media graphs keep one preferred candidate per kind so
  DRM video is refused closed instead of dropped; ffprobe DRM tags populate
  `MediaProbe.drm_signals`; PNG→JPEG conversion requires `allow_lossy`;
  event payloads reject forbidden keys inside tuples; support bundles
  include zero-UUID queue events; gallery pause/resume treats gallery-dl
  image sources as covering the gallery checkpoint. Mixed clear-then-key
  HLS still records the clear prefix and does not fetch encrypted parts.
- GitHub Actions `32575303382` on `e5cd48d` passed Python (605 pytest,
  100%), doctor provider probes, and Swift (18 tests, 0 failures; 12×
  BUILD SUCCEEDED) after requiring confirmed companion pairing headers
  even with the Mac loopback bearer, and after refusing HTTPS / extra-label
  relay URLs.
- Companion `/v1/companion` still requires the Mac actor, and pairing
  headers on that path must be a confirmed pairing even when the Mac
  loopback bearer is present. Relay URLs must be `http` private LAN,
  `.local`, or loopback; HTTPS and extra-label hosts such as
  `10.0.0.1.example.com` are refused.
- Swift `WebMediaDLExportIntent` shares the Python alphanumeric
  `container_preference` allowlist (1–12) and refuses hostile JSON decode.
- CLI `--container` and `POST /v1/jobs` / `/v1/plan` refuse hostile
  `container_preference` values with exit 1 / HTTP 422.
- GitHub Actions `32574304361` on `c255db7` passed Python (602 pytest, 100%),
  doctor provider probes, and Swift (18 tests, 0 failures; 12× BUILD
  SUCCEEDED), including PATH-isolated wheel doctor BLOCKED status from
  `fa17c6a`.
- Isolated wheel installs report yt-dlp / gallery-dl `BLOCKED` and do not
  download them. Linux CI doctor JSON also asserts telemetry off and Apple /
  signing / store / legal / original-pack `BLOCKED`.
- GitHub Actions `32574079043` on `2628c2f` passed Python (602 pytest, 100%),
  executed `webmedia-dl doctor` with yt-dlp / gallery-dl / ffmpeg version
  probes PASS, and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED).
- GitHub Actions `32573782710` on `2ee51ec` passed Python (600 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after fail-closing
  `container_preference` and installing `yt-dlp` / `gallery-dl` in CI.
  Exported JSON Schema now documents that allowlist on the string branch
  only. Linux CI executes `webmedia-dl doctor` and requires those provider
  version probes to PASS while signing, stores, App Review, legal review,
  and the original pack ZIP stay BLOCKED.
- Fail-close `container_preference` to an alphanumeric extension (1–12) and
  keep remux/convert outputs inside staging. Add `yt-dlp` and `gallery-dl` to
  the developer/CI toolchain so `webmedia-dl doctor` can PASS those version
  probes on Linux. Bind OpenSpec capability names across `.openspec.yaml`,
  `scripts/validate_bundle.py`, and spec directories, and bind the platform
  matrix keys to every `Surface` except CLI.
- GitHub Actions `32572904900` on `7981aaa` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after recording
  `32572653043` compile evidence for the `0f40550` evidence-cite revision.
- GitHub Actions `32572653043` on `0f40550` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after recording
  `32572254327` compile evidence for publishable history and job inspect.
- GitHub Actions `32572254327` on `2e5cd5b` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after keeping
  history, `webmedia-dl job`, and `GET /v1/jobs/{id}` on publishable
  `JOB_COMPLETED` artifact ids.
- GitHub Actions `32571904208` on `d5fee40` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after merging
  same-digest provenance and listing only publishable `JOB_COMPLETED` ids on
  `GET /v1/jobs/{id}`. History and `webmedia-dl job` now use those same
  publishable ids instead of unioning unpublished `SOURCE_REGISTERED` sources.
- GitHub Actions `32569815075` on `91eeb25` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after decoding plan
  JSON objects instead of matching escaped slashes. Same-digest registrations
  now always merge occurrences and parent ids, and `GET /v1/jobs/{id}`
  `artifact_ids` lists only `JOB_COMPLETED` publishable artifacts.
- GitHub Actions `32569700666` on `ae33eda` passed Python (583 pytest, 100%)
  and failed Swift: plan-body assertions compared raw JSON text to
  `https://example.com/a.mp4`, but Apple `JSONSerialization` escapes `/`.
  Contract tests now decode the plan JSON object.
- GitHub Actions `32569147243` on `5932ebc` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after speaking every
  App Intent result. Complete clients now explain the safest best-quality plan
  (`POST /v1/plan`) and run worker doctor (`GET /v1/doctor`) on the saved
  private Mac URL; macOS uses the loopback worker. Missing pairing fails closed.
  Watch/tv stay companion-only and do not call `/v1/plan`.
- GitHub Actions `32568400311` on `b2839e6` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after hopping
  complete-client queue buttons onto `WebMediaDLCompleteClientControl`.
- Complete-client history now returns a spoken job list instead of `"ok"`.
  Siri/Shortcuts on every Apple shell speak the worker or Mac-relay response.
  Last-job JSON inspect (`GET /v1/jobs/{id}`) fails closed without pairing or a
  job UUID, matching cancel/pause/resume.
- GitHub Actions `32568126057` on `f474719` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after boxing Mac
  worker spawn as `@Sendable` `WebMediaDLUncheckedBox`. Complete-client queue
  buttons share `WebMediaDLCompleteClientControl` with Siri/Shortcuts so pause
  without a saved Mac relay fails closed before any POST.
- GitHub Actions `32567922144` on `6516591` passed Python (583 pytest, 100%)
  and failed Swift 6: `startOrClaimExisting` still took a non-Sendable
  `() throws -> AnyObject` start closure. Spawn now returns
  `WebMediaDLUncheckedBox<AnyObject>` from a `@Sendable` start, matching share
  extensions. `32567533760` on `6aad227` failed because
  `WebMediaDLMacWorkerLaunch` (`started(AnyObject)`) is not Sendable.
  The launch enum is `@unchecked Sendable` and `startMacWorker` applies UI
  updates with `MainActor.run` after the nonisolated spawn/claim. Complete-client
  Siri/Shortcuts controls share
  `WebMediaDLCompleteClientControl` so unknown kinds, cancel without a UUID,
  and pause without a saved Mac relay fail closed before transport.
- GitHub Actions `32567291154` on `9e8a154` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after proving iPhone
  watch-forward in Core. Watch/tv control intents share
  `WebMediaDLCompanionControlMessage` so unknown kinds and cancel without a
  UUID fail closed before transport. Mac worker supervision
  `startOrClaimExisting` claims a healthy loopback worker and keeps the spawn
  error when health is not ok.
- GitHub Actions `32566998821` on `2a5357c` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) for throwing JSON
  request builders. iPhone watch-forward is a Core coordinator that XCTest
  proves: typed companion messages reach the Mac send path, and cancel
  without a job UUID never forwards. App Intents share
  `WebMediaDLCompanionJobControl.requireJobId`.
- GitHub Actions `32566609235` on `159b3ce` passed Python (583 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) for LAN malformed
  JSON, companion persist/load, Files `replaceItemAt`, and the 159-path
  inventory digest pin. JSON POST builders now throw through `jsonBody`
  instead of `try?` encoding, so a non-serializable payload never leaves as
  an empty body.
- GitHub Actions `32565897471` on `786e78c` passed Python (582 pytest, 100%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED) after hopping iPhone
  watch-forward onto the main actor. Malformed LAN JSON no longer skips
  `nativeCommand` checks; companion relay persist/load fail closed; Files
  commits use `replaceItemAt` so a failed overwrite keeps the previous file;
  pack inventory pins the 159-path digest and rejects directories. Coverage
  `fail_under` is 100 after that GitHub HEAD report. Local `uv run pytest --cov`
  is 583 tests at 100%.
- iPhone watch-forward hops `WCSession` `userInfo` onto the main actor before
  mutating SwiftUI state (GitHub `32565480088` on `7088fda` compiled Python
  and failed iOS device Swift 6 with `status` mutated from a nonisolated
  callback). JSON POSTs without a body, sealed companion envelopes missing
  nonce/ciphertext/mac, Continuity `send` non-2xx, and Safari native-handler
  encode/HTTP failures fail closed. GitHub `32565480088` (`7088fda`) Python
  was 582 tests at 100%; Swift 6 failed the iOS MainActor status mutation.
  Local `uv run pytest --cov` stays at `fail_under` 99 until GitHub HEAD
  also reports a green Swift job.
- On-device `HttpDirect` transfers HTTPS only, disables cookies, bounds
  redirects, and refuses non-2xx (including 3xx) bodies so cancelled redirects
  cannot publish HTML. Loopback and paired-Mac `send` plus history decode fail
  closed on non-2xx and malformed job lists. Complete-client queue, share, and
  iPhone watch-forward surfaces use `do/catch` instead of swallowing `try? await`
  (Swift 6 refuses non-Sendable `displayedResponse` closures in those views).
  Watch/tv history decode fails closed instead of becoming `[]`. yt-dlp non-zero
  exits quarantine partial output when a file exists and skip quarantine when it
  does not. The Mac app no longer activates `WCSession`; watch messages stay
  watch → iPhone → Mac LAN HTTP. GitHub Actions `32564115037` on `7b909d0`
  passed Python (580 pytest, 99%) and Swift (18 tests, 0 failures;
  12× BUILD SUCCEEDED). `32565220846` on `8cc0172` passed Python and failed
  Swift 6 `displayedResponse` Sendable checks. Local `uv run pytest --cov` is
  582 tests at 100% (`fail_under` stays 99 until GitHub HEAD also reports 100%).
- Files `ExportIntent` path bounds use the same standardized `allows()` check
  as security-scoped bookmarks, so `/approved/../escape` is denied. On-device
  `HttpDirect` requires an `http`/`https` host and refuses the worker's blocked
  schemes before fetch. The Mac app claims an existing loopback worker only
  after `GET /health` returns `{"status":"ok"}`. Cancel/pause_job/resume_job
  App Intents throw when the job id is not a UUID instead of succeeding as a
  no-op. Queue pause/cancel CAS retries until `TRANSITION_ATTEMPTS` is exhausted.
  Local `uv run pytest --cov` is 580 tests at 100% (`fail_under` stays 99 until
  GitHub HEAD also reports 100%).
- GitHub Actions `32563044217` on `c347068` passed Python (578 pytest, 99.97%)
  and Swift (18 tests, 0 failures; 12× BUILD SUCCEEDED). Unsigned
  `xcodebuild` produced Mach-O share-sheet `.appex` products (`iphoneos`/`xros`
  64-bit, Mac fat) with package type `XPC!`. Signed NSExtension wrapping, device
  UI, PhotoKit writes, and WatchConnectivity radio stay BLOCKED. Local
  `uv run pytest --cov` is 578 tests at 99.99%.
- GitHub Actions `32562009351` on `32c8d97` passed Python (577 pytest, 99.97%)
  and Swift (18 tests, 0 failures; 8× BUILD SUCCEEDED) for unsigned share-extension
  `.appex` layouts. `32562777675` on `63a7661` passed Python and failed Swift
  because app-extension targets must set `APPLICATION_EXTENSION_API_ONLY=YES`.
- GitHub Actions `32561499120` on `6d90ce4` passed Python (574 pytest, 99.97%)
  and Swift (18 tests, 0 failures; 8× BUILD SUCCEEDED). That revision keeps the
  Mac worker data directory behind `#if os(macOS)` after `32561025265` /
  `882169a` failed iOS compile on `homeDirectoryForCurrentUser`. Complete-client
  LAN jobs send pairing headers only; the Mac relay strips `Authorization` /
  `X-WebMedia-Token`, injects the loopback bearer solely for `/v1/companion`
  after pairing, and refuses `/v1/pair/confirm`. Swift events decode JSON values
  the way Python `EventRecord.payload` does, including nested provider-console
  keys. Local `uv run pytest --cov` is 574 tests at 99.99%.
- Complete-client URL jobs with a Files bookmark submit `staging_only` to the Mac
  worker. A phone sandbox `files_app` path is refused. Published artifacts are
  pulled with `GET /v1/artifacts/{id}/content` into the local Files bookmark.
  Swift events reject provider-console payload keys; SOURCE artifacts must be
  `sha256:<digest>`. Files bookmark `allows()` requires an absolute root. The Mac
  app launches `webmedia-dl serve` on `127.0.0.1:8765` when the binary is on PATH.
  GitHub Actions `32560244195` on `5cb2090` passed Python (571 pytest, 99.97%) and
  Swift (18 tests, 0 failures; 8× BUILD SUCCEEDED). Local `uv run pytest --cov` on
  this revision is 573 tests at 99.99%.
- Stale or unresolvable Files bookmarks raise `destinationDenied`; empty roots
  stay `filesDestinationRequired`. Cookie grants fail closed when the file is
  missing, unresolvable, or the path changed after issue. Queue `set_state`
  reads pause/cancel flags without re-parsing evidence. Submit claims inside
  `_run` so a monkeypatched wait path still returns `ACCEPTED`. Local
  `uv run pytest --cov` is 571 tests at 99.99%. GitHub Actions `32556972304` on
  `54c90dc` passed Python (564 pytest, 99.99%) and Swift (18 tests, 0 failures;
  8× BUILD SUCCEEDED). GitHub Actions `32556536991` on `44b46ac` failed `ty`
  and Swift HttpDirect.
- Pause and cancel after `publishing` fail closed so publication cannot finish
  as `paused`/`cancelled`. tvOS companion messages use a Mac LAN transport
  rather than WatchConnectivity; the iPhone companion app forwards watch
  userInfo to the paired Mac relay. Cancel/pause_job/resume_job companion
  messages require a job UUID at send time. Complete-client share drops upload
  bytes to `POST /v1/staging` with a sha256 digest and submit the Mac staging
  path; a phone sandbox `file://` path is not queued. The LAN relay keeps a
  1 MiB JSON cap and a separate staging byte bound. App and share-extension
  `PrivacyInfo.xcprivacy` manifests declare UserDefaults reason `1C8F.1`.
- Queue `submit`/`resume_job` claim accepted jobs with the same `BEGIN IMMEDIATE`
  pause check as `run_next`. Cookie grants are revalidated on resolve. Malformed
  browser evidence fails the job. Checkpoint `acquired_kinds` must match restored
  sources. Missing resolved provider binaries are `missing`, not `healthy`.
  Bundle validation refuses to extract unsafe zip members. HttpDirect fails closed
  on unresolvable bookmark data; share extensions `cancelRequest` on submit
  errors; LAN relay refuses unclassified peers; Mac entitlements include
  `network.server`; complete-client plists declare local-network use. OpenSpec
  binds remaining Linux-provable SHALLs to named tests. GitHub Actions run
  `32555270688` on `89f7492` passed Python (550 pytest, 99.98%) and Swift
  (18 tests, 0 failures; 8× BUILD SUCCEEDED).
- Provider `_tracked_run` clips stdout/stderr to 8 MiB on every return.
  OpenSpec binds remux-before-transcode, sibling publication isolation,
  cookie-grant restore, unsafe format ids, and doctor BLOCKED release
  gates. GitHub Actions run `32554995796` on `b6a1cc6` passed Python
  (550 pytest, 99.98%) and Swift (18 tests, 0 failures; 8× BUILD
  SUCCEEDED).
- Exit 0 with no source files fails closed as "produced no source files"
  instead of "exited 0". Existing `output_paths` still register when the
  primary `output_path` is missing. Live recording polls with a `while`
  bound. OpenSpec binds queue zero-UUID events and `wmdl` not being the
  console script. GitHub Actions run `32554995796` on `b6a1cc6` passed
  Python (550 pytest, 99.98%) and Swift (18 tests, 0 failures; 8× BUILD
  SUCCEEDED).
- A clear acquire probe that later reports encryption fails closed at
  `_record_probe`. Lossy transcode skips semantic-parity. HLS byte-range
  clocks always advance after a parsed `#EXT-X-BYTERANGE` length. Staging
  skips resolved paths outside the job root. GitHub Actions run
  `32554995796` on `b6a1cc6` passed Python (550 pytest, 99.98%) and Swift
  (18 tests, 0 failures; 8× BUILD SUCCEEDED).
- Envelope nonce ledger prunes rows older than 24h on open and consume so
  `nonces.sqlite` cannot grow without bound. OpenSpec scenario titles map to
  `(path, test)` evidence. Unreachable URL-as-path and DASH timeline branches
  are removed; publication refuses unknown destination kinds. Restored preview
  artifacts are skipped at validation; acquired-kinds without sources fail closed.
  GitHub Actions run `32554995796` on `b6a1cc6` passed Python (550 pytest,
  99.98%) and Swift (18 tests, 0 failures).
- Companion cancel/pause_job/resume_job require a job UUID (sealed
  envelopes included). `/v1/companion` forbids extra JSON fields such as
  `providerArgv`. `doctor` records an executed httpx probe for
  `http-direct`. `validate.container` health follows ffprobe. File/drop
  intake refuses `http(s)` locators. Expired pairing records are pruned.
  Bundle zips skip sqlite databases.
- DASH `$Number$` templates expand through `endNumber` or Period /
  `mediaPresentationDuration` (capped at 64 segments). Provider stdout/stderr
  is clipped to 8 MiB before logging. GitHub Actions run `32552988266` on
  `f3fd795` passed Python (529 pytest) and Swift (18 tests, 0 failures).
- Confirmed iPhone/iPad/visionOS pairing keeps `personal-restricted` on the job
  record while the Mac worker executes yt-dlp. Unconfirmed pairing still denies
  delegation. Fetch follows redirects hop-by-hop under `authorize_url` (no
  `file:`/`http:` escape). `require_pass` always demands executed hash and size
  PASS. Pairing and worker data dirs are `0700`; pairing/token/artifact indexes
  are `0600`. Queue control and pair bodies `extra=forbid` and reject
  `nativeCommand`. Doctor reports `tools.ffprobe`. Bundle zips skip `.env` and
  key material. Provider staging ignores symlinks out of the job directory.
  GitHub Actions run `32552988266` on `f3fd795` re-proved that pairing path
  (529 pytest; 18 Swift tests, 0 failures).
- Mac, iPhone, iPad, and visionOS App Intents pause, resume, history, status,
  cancel, and per-job pause/resume through the same worker/relay paths as the
  in-app queue controls. watchOS and tvOS cancel, pause_job, and resume_job
  App Intents include a job UUID. GitHub `macos-15` run `32552988266` (`f3fd795`,
  18 tests, 0 failures) compiled those intents. Prior queue App Intents compiled
  on run `32550239808` (`24aeb5c`).
- watchOS and tvOS App Intents queue pause, resume, history, status, and
  cancel companion kinds in addition to capture. GitHub `macos-15` run
  `32550050185` executed Core `swift test` (18 tests, 0 failures) on
  `fa1dee6`.
- App Intents restore the same App Group Files bookmark as share sheets.
  `destination_kind=share` publishes under approved roots. GitHub `macos-15`
  run `32549540515` executed Core `swift test` (18 tests, 0 failures) on
  `7edfb8e`.
- Share sheets restore the App Group Files bookmark through
  `WebMediaDLShareIntake.fromSavedBookmark` so complete-client share adapters
  carry `files_app` destinations. OpenSpec scenarios cover Mac-relay history,
  fixed bundle timestamps, encrypted HLS refuse-before-fetch, and default
  telemetry rejection. GitHub `macos-15` run `32549087599` executed Core
  `swift test` (18 tests, 0 failures) on `fea26f1`.
- Mac LAN HTTP relay binds private/loopback addresses, rewrites onto the
  loopback worker, refuses public peers and `nativeCommand`, and advertises
  paste URLs in the Mac app. Complete-client history and queue controls use
  that relay instead of the phone's loopback. GitHub `macos-15` run
  `32548815452` executed Core `swift test` (18 tests, 0 failures) on `8f075d1`.
- Source artifacts reject non-`sha256:<digest>` ids; capability health probes
  binary versions; complete clients send heavy work to a saved Mac relay URL
  instead of the phone's loopback; the extension popup send button is proven
  under Node. GitHub `macos-15` run `32548311255` executed Core `swift test`
  (18 tests, 0 failures) and built the Apple packages on `cf41473`.
- Queue SQLite transactions start with `BEGIN IMMEDIATE`, and `claim_next`
  commits only after `UPDATE … RETURNING`, so concurrent workers cannot
  double-claim the same accepted job.
- Complete-client http-direct binds the calling surface, chunks URLSession
  bytes, and share sheets on iPhone/iPad/visionOS try on-device save first.
- Bundle validation executes START_HERE link, task DAG, traceability, archive
  safety, and clean-extraction gates; stream-copy exports require semantic
  parity; ImageMagick convert runs under the packaged policy.
- Complete-client `http-direct` streams under the byte bound, sanitizes Files
  output stems, and refuses stale bookmarks before write.
- Implement `build-webmedia-dl-v1` Python worker, CLI, schemas, tests, and overlay.
- Cooperative per-job pause checkpoints, mixed-media failure containment, and
  Mac-forwarded watchOS/tvOS companion messages.
- Speak/Siri intake, per-operation export checkpoints, HLS MAP/BYTERANGE,
  DASH SegmentTimeline recording, and in-flight provider cancel.
- DASH/HLS rendition selection prefers the highest-bandwidth video (or audio)
  Representation; watchOS/tvOS queue companion messages for Mac relay; share
  extensions extract HTTPS locators versus file drop paths.
- Multi-period DASH concatenates the selected video from each Period; companion
  POST accepts a one-time AES-GCM pairing envelope; visionOS share and complete
  client Files destinations use the same security-scoped path contract.
- Share extensions expose `NSExtensionRequestHandling` principals; Files
  destinations persist security-scoped `bookmarkData`; watch/tv send typed
  companion messages through a queued transport; history views decode
  `WebMediaDLHistoryEntry`; intents load stored worker credentials.
- Pairing keeps the client profile (no restricted-to-full widening) and requires
  a session key; cookies are job-bound grants, not raw paths; probe-detected
  encryption refuses closed before export.
- Queue-global pause holds per-job resume in `accepted`; live recording enforces
  an aggregate byte bound, records separate audio/video artifacts, uses yt-dlp
  for live watch pages, and concatenates multi-period SegmentBase/SegmentList
  occurrences in order.
- Export remuxes first and transcodes the original only if remux cannot satisfy
  the container; container gates use ffprobe evidence, not filename suffixes;
  `package-extensions` ships from packaged `runtime/extensions` in a wheel.
- Discovery covers picture/source MIME, AMP media, JSON-LD URL lists, and a
  provided-HTML byte cap; `plan --container` explains the export DAG; support
  bundles recursively strip console/cookie fields; `updates` checks PyPI without
  installing; migration recursively indexes every allowlisted archive marker.
- Cookie grants persist across worker processes; yt-dlp dump-json uses the same
  job-bound grant; a failed publish sibling does not abort other validated
  outputs. Apple share principals await NSItemProvider load, Files bookmarks
  resolve and standardize paths, and watch/tv decode typed companion history
  over WatchConnectivity scaffolding.
- Mandatory validation rejects `BLOCKED` and empty evidence; cookie grants merge
  under a file lock at mode `0600`; empty approved roots no longer authorize
  cwd. watchOS/tvOS speak intents use companion transport; Mac restores Files
  bookmarks and activates `WCSessionDelegate`; share extensions ship App Group
  entitlements; `companion capture <locator>` accepts a positional URL.
- Packaged runtime falls back to checkout resources without a `runtime/` tree;
  live recording fails closed on HTTP 400 playlists, empty segments, and
  nested/audio stop; CLI paste/speak DRM locators and missing drops exit 1;
  export policy errors still publish the original source. Redirect bounds,
  unresolved cookie grants, paused `claim_next`, and missing provider binaries
  fail closed with executed tests. Missing checkpoint artifacts, preview-only
  exports, `include_original=false`, validation failures, queue schema
  migration, claim CAS misses, later live-poll DRM, and worker API pairing
  errors fail closed with executed tests. Cancel during acquire, all-kind
  DRM failure, SOURCE validation skip with derivative publish, and ffmpeg
  probe DRM fail closed with executed tests. Export pause checkpoints,
  already-acquired kind skip, duplicate failed-kind containment, derivative
  validation skip with source publish, optional dependent skip, DASH
  video/audio kind split, live poll stop, and HTML gallery/embed discovery
  fail closed with executed tests. Queue-paused resume, empty output_paths
  fallback, Photos/staging publication guards, probe timeout/encrypted tags,
  and URL-never-path source validation fail closed with executed tests. Empty
  HTML srcset tokens are skipped; ffmpeg `%(ext)s` stem matching uses a dummy
  suffix; cookie-ledger JSON, probe encryption fields, packaging directories,
  unresolved cookies, and resume without restored sources fail closed with
  executed tests. Leftover DASH media without a SegmentTemplate is recorded;
  supplied HLS parts still refuse AES-128 on inspect; resume from
  `stage=exporting` restores `produced_ids`. Forbidden export loss classes
  cannot be planned; SegmentTimeline without `t` keeps a running clock.
  Cooperative cancel/pause during subprocess `TimeoutExpired` stops the
  provider; export progress accepts a null artifact and duplicate operation
  keys; duplicate `produced_ids` at `stage=exported` still complete; acquired
  remote resume does not refetch. ImageMagick health/argv accept IM6 `convert`.
  Worker API job-detail and run-next payloads are module helpers. GitHub
  `macos-15` CI on `94e423b` executed Core `IdentityTests` (6 tests, 0
  failures). Core contract tests cover nativeCommand refuse, Photos closed,
  history envelopes, and bookmark denial. CI builds the Mac package and
  typechecks the remaining Apple packages including share extensions.
  WatchConnectivity types keep a single class header and conform to
  `WCSessionDelegate` via extensions. Encrypted HLS `#EXT-X-SESSION-KEY`
  (FairPlay SAMPLE-AES) is refused before segment fetch; `detect_drm_signals`
  matches `cenc`, Widevine/PlayReady UUIDs, and `skd://`. `acquire.gallery_dl`
  requires `subprocess_capable`. Files destinations require a security-scoped
  bookmark whose path stays inside approved roots. Doctor runs a real
  `-version`/`--version` probe (`FAIL` on probe error, `WARN` for IM6
  `convert`). Provider argv is allowlisted for every binary; format ids cannot
  start with `-`. ImageMagick policy denies MSL/MVG/URL/FTP and all delegates.
  Share-extension principals box `NSExtensionContext` for Swift 6 sending.
  Coverage `fail_under` is 99. Pairing `personal-full`/unknown profiles return
  400; companion unknown job ids return 404; envelope payloads must be JSON
  objects. Dynamic DASH stops remaining renditions after late
  ContentProtection; growing HLS byte-ranges refetch and append only the new
  suffix. Probe-discovered encryption is terminal (quarantine, no yt-dlp
  fallback). Publication `OSError` fails the durable job. CLI unknown
  job/cancel/pause/resume/companion and DRM `plan` exit 1. AppIntent titles
  are `static let`; companion `forward`/`forwardSealed` take the relay by
  value for Swift 6. `AppShortcutsProvider` lists `AppShortcut` statements
  via the result builder (no array literal, no commas between shortcuts).
  Share-extension targets are library products depended on by each complete-client
  executable so `macos-15` `xcodebuild` compiles them when SwiftPM omits a scheme.
  Live byte-range refetch HTTP errors fail closed; overlapping already-written
  ranges are not rewound; `run_next` restores the job-bound cookie grant.
  visionOS WatchConnectivity implements `sessionDidBecomeInactive` /
  `sessionDidDeactivate`. `serve_worker` refuses non-loopback hosts. Sealed
  companion envelopes still refuse `nativeCommand`. `original-sacred` keeps
  `keep-original` at `LossClass.NONE` with no transcode. Shared Swift Core
  types now carry the same JSON keys as the exported Pydantic schemas
  (`WebMediaDLPipelineJob`, operations, policy fetch bounds, history timestamps).
  OpenSpec scenarios map to named Python or Swift tests; shipped provider
  manifests never auto-install or accept user argv. `recordable_parts` always
  refuses DASH UUID/cenc and HLS session keys (no inspect-skip DRM bypass).
  Capture popup markup is parsed (lang, labeled token, status+aria-live);
  `drop` records the resolved `local_path`; local submit JSON has no telemetry
  upload and makes no HTTP calls; `/v1/jobs` forbids `nativeCommand`/`providerArgv`.
  GitHub `macos-15` CI run `32543981785` on `691114e` compiled Core tests (18/0,
  including schema-aligned domain assertions) and every Apple package including
  tvOS.
