# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32561772584` on `31b9296` compiles Core tests and Apple packages (18 tests, 0 failures; 8× BUILD SUCCEEDED). Unsigned share-extension `.appex` layouts are assembled for inspection; signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
