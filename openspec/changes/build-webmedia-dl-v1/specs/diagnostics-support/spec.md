# Delta: diagnostics-support

## ADDED Requirements

### Requirement: Evidence-qualified doctor

`webmedia-dl doctor` SHALL report `PASS` / `WARN` / `BLOCKED` / `FAIL` using the
pack legend. Unavailable Apple devices, stores, signing, notarization, App Review,
and legal review SHALL be `BLOCKED`, never `PASS`.

#### Scenario: doctor JSON

- **WHEN** doctor runs on Linux CI
- **THEN** `telemetry_default` is false, `drm_circumvention` is false, and
  `apple_devices.macos.status` is `BLOCKED`
