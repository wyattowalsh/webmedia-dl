# W7 evidence

- status: `BLOCKED`
- scope: Apple package compile and device runtime.
- reason: GitHub `macos-15` run `32566609235` on `159b3ce` compiles Core tests and Apple packages (18 tests, 0 failures; 12× BUILD SUCCEEDED) after LAN JSON, companion persist, and Files `replaceItemAt` fail-closed. Signed NSExtension wrapping, device UI, PhotoKit writes, and WatchConnectivity radio are not executed.
