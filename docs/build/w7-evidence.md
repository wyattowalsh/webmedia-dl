# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32565897471` on `786e78c` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after the MainActor watch-forward fix. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
