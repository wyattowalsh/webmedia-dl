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
| watchOS / tvOS | Capture, status, history, pause/resume/cancel controls | Never subprocess workers |

Loopback worker: `http://127.0.0.1:8765`. The Mac app also listens on a private
LAN/loopback HTTP relay (`http://127.0.0.1:8766` plus private interface URLs) that
rewrites onto that worker and refuses public peers and `nativeCommand`. Complete
clients paste one of those advertised URLs. Complete clients also run on-device
`http-direct` (`URLSession`, HTTPS only, cookies disabled, at most five redirects)
into a user-approved Files bookmark for locators that already name a media object.
Share sheets restore that Files bookmark via `WebMediaDLShareIntake.fromSavedBookmark`
so on-device HTTP still writes there. Heavy complete-client jobs submit `staging_only`
to the Mac worker; a phone sandbox `files_app` path is not a Mac destination. After
the Mac job publishes, complete clients pull artifact bytes from
`GET /v1/artifacts/{id}/content` into that same Files bookmark. Page locators,
encrypted HLS/DASH, and live manifests fail closed locally and require a paired Mac.
Watch companion messages travel watch → iPhone `WCSession` → Mac LAN HTTP; the Mac
app does not activate `WCSession`. tvOS capture is typed URL only (`UIPasteboard` is
unavailable). Photos/Files/Share destinations require a user-approved root. Swift
packages are under `apps/`. GitHub `macos-15` CI runs Core `swift test`, builds the
Mac package including the share-extension library product, typechecks
iOS/iPadOS/visionOS/watchOS/tvOS packages, and `xcodebuild`s unsigned
`com.apple.product-type.app-extension` share-sheet `.appex` products from
`apps/WebMediaDLShareExtensions`. Share extensions stay library products depended on
by each executable so SwiftPM scheme gaps still compile, and the unsigned
app-extension project produces inspectable Mach-O `.appex` bundles. Apple device
runtime, signing, and store submission stay BLOCKED.
