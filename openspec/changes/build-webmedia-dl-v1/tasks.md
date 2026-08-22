# Tasks

Implementation tasks for `build-webmedia-dl-v1`.

- [x] TASK-001 Implement `accessibility-ux` contracts and tests
- [x] TASK-002 Implement `acquisition-adapters` contracts and tests
- [x] TASK-003 Implement `apple-platform-clients` contracts and tests
- [x] TASK-004 Implement `apple-system-integrations` contracts and tests
- [x] TASK-005 Implement `asset-store-provenance` contracts and tests
- [x] TASK-006 Implement `browser-extensions` contracts and tests
- [x] TASK-007 Implement `cross-device-workers` contracts and tests
- [x] TASK-008 Implement `diagnostics-support` contracts and tests
- [x] TASK-009 Implement `discovery-candidates` contracts and tests
- [x] TASK-010 Implement `export-planning` contracts and tests
- [x] TASK-011 Implement `export-validation-publication` contracts and tests
- [x] TASK-012 Implement `intake-routing` contracts and tests
- [x] TASK-013 Implement `live-manifest-recording` contracts and tests
- [x] TASK-014 Implement `media-processing` contracts and tests
- [x] TASK-015 Implement `migration-compatibility` contracts and tests
- [x] TASK-016 Implement `packaging-distribution-updates` contracts and tests
- [x] TASK-017 Implement `queue-events-observability` contracts and tests
- [x] TASK-018 Implement `security-privacy-policy` contracts and tests
- [x] TASK-019 Export JSON Schemas from Pydantic models
- [x] TASK-020 CLI `doctor` / `submit` / `serve` loopback worker
- [x] TASK-021 Bundle validator and reproducible zip packager

> [!NOTE]
> Apple device runtime, App Store, browser-store submission, signing, notarization,
> and human legal review remain `BLOCKED` on Linux CI. Native SwiftUI shells and the
> Core package are in `apps/`. GitHub `macos-15` CI runs Core `swift test`, builds
> the Mac package and share-extension library, typechecks the remaining Apple
> packages, and `xcodebuild`s unsigned `com.apple.product-type.app-extension`
> share-sheet `.appex` products. Share-extension targets are library products
> depended on by each complete-client executable so missing SwiftPM schemes still
> compile; signed NSExtension wrapping stays BLOCKED.
