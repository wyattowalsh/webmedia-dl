# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32572653043` on `0f40550` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after recording `32572254327` publishable history and job-inspect evidence. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
