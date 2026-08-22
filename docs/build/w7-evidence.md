# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32563044217` on `c347068` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) and `xcodebuild`s unsigned `com.apple.product-type.app-extension` share-sheet `.appex` Mach-O products. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
