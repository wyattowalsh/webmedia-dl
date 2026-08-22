# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32574079043` on `2628c2f` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after documenting the container allowlist in JSON Schema and executing doctor provider probes. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
