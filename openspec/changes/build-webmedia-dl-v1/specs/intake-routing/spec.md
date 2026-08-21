# Delta: intake-routing

## ADDED Requirements

### Requirement: Typed intake without retrieval

Intake SHALL classify and normalize locators into `MediaSource` records. It SHALL NOT
perform network retrieval. `file:` URLs SHALL be rejected as URL intake.

#### Scenario: HTTPS paste

- **WHEN** the CLI receives `https://example.com/a.png`
- **THEN** the source has `normalized_url` set and `local_path` unset

#### Scenario: file scheme rejected

- **WHEN** intake receives `file:///tmp/secret.png` as a URL
- **THEN** it fails closed with `IntakeError`

### Requirement: URL is never a filesystem path

A network locator SHALL NOT be copied into `local_path`.

#### Scenario: URL plus path is invalid

- **WHEN** a `MediaSource` is constructed with both a URL kind and `local_path`
- **THEN** validation fails
