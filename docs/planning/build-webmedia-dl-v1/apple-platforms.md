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

Loopback only: `http://127.0.0.1:8765`. Photos/Files/Share destinations require a user-approved root. Swift packages are under `apps/`. GitHub `macos-15` CI runs Core `swift test`, builds the Mac package, and typechecks iOS/iPadOS/visionOS/watchOS/tvOS packages. Apple device runtime, signing, and store submission stay BLOCKED.
