# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32572254327` on `2e5cd5b` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after publishable history and CLI job inspect ids. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
