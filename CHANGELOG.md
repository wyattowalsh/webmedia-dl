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
