# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32574304361` on `c255db7` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED), including PATH-isolated wheel doctor BLOCKED status from `fa17c6a`. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
