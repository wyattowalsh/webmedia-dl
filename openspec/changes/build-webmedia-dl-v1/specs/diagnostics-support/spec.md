# Delta: diagnostics-support

## ADDED Requirements

### Requirement: Evidence-qualified doctor

`webmedia-dl doctor` SHALL report `PASS` / `WARN` / `BLOCKED` / `FAIL` using the
pack legend. Unavailable Apple devices, stores, signing, notarization, App Review,
and legal review SHALL be `BLOCKED`, never `PASS`.

#### Scenario: doctor JSON

- **WHEN** doctor runs on Linux CI
- **THEN** `telemetry_default` is false, `drm_circumvention` is false, and
  `apple_devices.macos`, `signing_notarization`, `browser_stores`, `app_review`,
  `legal_review`, and `original_planning_pack` are `BLOCKED`

### Requirement: Local support bundle

`webmedia-dl support-bundle` SHALL write a local zip of doctor output, jobs, and
typed events. It SHALL NOT upload telemetry or include raw provider console
streams (`stdout` / `stderr` / `argv`).

#### Scenario: support bundle is local-only

- **WHEN** `webmedia-dl support-bundle --out` writes a zip
- **THEN** the JSON result has `telemetry` false and the zip contains `doctor.json`
