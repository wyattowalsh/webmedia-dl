# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32568400311` on `b2839e6` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after hopping complete-client queue buttons onto `WebMediaDLCompleteClientControl`. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
