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
  Worker API job-detail and run-next payloads are module helpers. Core Swift
  tests run on GitHub `macos-15` CI. WatchConnectivity types keep a single
  class header and conform to `WCSessionDelegate` via extensions.
