# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32569147243` on `5932ebc` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after speaking App Intent results. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
