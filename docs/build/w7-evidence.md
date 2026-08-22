# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32572904900` on `7981aaa` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after recording `32572653043` evidence-cite compile. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
