# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32561025265` on `882169a` failed iOS `xcodebuild` because `FileManager.homeDirectoryForCurrentUser` is unavailable on iPhoneOS. Last both-green compile is `32560244195` on `5cb2090` (18 tests, 0 failures; 8× BUILD SUCCEEDED). This follow-up keeps the Mac worker data directory behind `#if os(macOS)`. Device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
