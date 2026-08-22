# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32571904208` on `d5fee40` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after provenance merge and publishable job-detail ids. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
