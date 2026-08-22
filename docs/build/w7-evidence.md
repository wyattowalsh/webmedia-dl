# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32569815075` on `91eeb25` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after decoding plan JSON objects. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
