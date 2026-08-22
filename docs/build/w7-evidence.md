# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32556972304` on `54c90dc` compiles Core tests and Apple packages (18 tests, 0 failures; 8× BUILD SUCCEEDED). Device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
