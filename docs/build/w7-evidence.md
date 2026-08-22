# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32561499120` on `6d90ce4` compiles Core tests and Apple packages (18 tests, 0 failures; 8× BUILD SUCCEEDED). GitHub `32561025265` on `882169a` failed iOS `xcodebuild` on `homeDirectoryForCurrentUser`; that API stays behind `#if os(macOS)`. Device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
