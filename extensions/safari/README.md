# Safari Web Extension

Safari uses the same `extensions/shared/capture.js` evidence collector.

The extension SHALL POST jobs to the loopback worker and SHALL NOT expose a
generic native command runner (`nativeMessaging` to arbitrary shells is out of
scope). Xcode wrapping remains BLOCKED on Linux CI.
