# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32568126057` on `f474719` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after boxing Mac worker spawn as `@Sendable` `WebMediaDLUncheckedBox`. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
