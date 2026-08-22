# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32573782710` on `2ee51ec` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after fail-closing container preference. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
