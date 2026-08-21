# Delta: security-privacy-policy

## ADDED Requirements

### Requirement: No DRM circumvention

Widevine, FairPlay, PlayReady, encrypted HLS, and cenc signals SHALL refuse closed.

### Requirement: Cookie access is explicit

Cookies SHALL require `CookieAccess.EXPLICIT_PATH`, an existing absolute file, and
MUST NOT live inside the repository. Restricted profiles SHALL set cookie access to
`never`.

#### Scenario: repo cookie rejected

- **WHEN** `--cookies` points at a file inside the repo
- **THEN** `CookiePolicyError` is raised

### Requirement: No default telemetry or auto-install

Policy profiles SHALL forbid `telemetry_default` and automatic provider installation.
