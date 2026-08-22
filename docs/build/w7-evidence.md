# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32562009351` on `32c8d97` compiles Core tests and Apple packages (18 tests, 0 failures; 8× BUILD SUCCEEDED) and assembles unsigned share-extension `.appex` layouts. This follow-up adds unsigned `xcodebuild` of `com.apple.product-type.app-extension` targets; signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
