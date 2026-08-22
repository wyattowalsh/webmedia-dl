# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32567291154` on `9e8a154` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED). `32567533760` on `6aad227` failed Swift 6 because `WebMediaDLMacWorkerLaunch` was not Sendable. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
