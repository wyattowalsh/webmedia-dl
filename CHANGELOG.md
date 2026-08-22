# Changelog

## 0.1.0

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
  `keep-original` at `LossClass.NONE` with no transcode.
