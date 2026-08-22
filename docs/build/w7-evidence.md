# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32566998821` on `2a5357c` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after JSON request builders throw through `jsonBody`. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
