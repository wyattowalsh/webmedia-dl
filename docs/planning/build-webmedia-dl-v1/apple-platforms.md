---
title: "Apple platforms"
status: proposed
type: planning
change: build-webmedia-dl-v1
last_reviewed: 2026-08-18
---
# Apple platforms

| Surface | Role | Heavy work |
|---|---|---|
| macOS | Full local worker + app, share sheet, App Intent | Runs yt-dlp/ffmpeg/gallery-dl when the profile allows |
| iPhone / iPad / visionOS | Complete clients | Lightweight HTTP locally; yt-dlp only after Mac pairing confirmation |
| watchOS / tvOS | Capture, status, history, pause/resume controls | Never subprocess workers |

Loopback worker: `http://127.0.0.1:8765`. The Mac app also listens on a private
LAN/loopback HTTP relay (`http://127.0.0.1:8766` plus private interface URLs) that
rewrites onto that worker and refuses public peers and `nativeCommand`. Complete
clients paste one of those advertised URLs. Complete clients also run on-device
`http-direct` (`URLSession`) into a user-approved Files bookmark for locators that
already name a media object. Share sheets restore that Files bookmark via
`WebMediaDLShareIntake.fromSavedBookmark` so heavy submit still carries
`files_app`. Page locators, encrypted HLS/DASH, and live
manifests fail closed locally and require a paired Mac. tvOS capture is typed URL
only (`UIPasteboard` is unavailable). Photos/Files/Share destinations require a
user-approved root. Swift packages are under `apps/`. GitHub `macos-15` CI runs
Core `swift test`, builds the Mac package including the share-extension library
product, and typechecks iOS/iPadOS/visionOS/watchOS/tvOS packages. Share
extensions are library products depended on by the executable so `xcodebuild`
compiles them even when SwiftPM does not auto-generate a scheme. Apple device
runtime, signing, and store submission stay BLOCKED.
