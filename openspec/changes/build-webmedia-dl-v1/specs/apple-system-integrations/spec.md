# Delta: apple-system-integrations

## ADDED Requirements

### Requirement: User-approved destinations

Share sheet, Files, and Photos destinations SHALL be user-approved roots. The worker
SHALL NOT silently write into the photo library or arbitrary home paths.

#### Scenario: publication requires approved roots

- **WHEN** `destination_kind` is `user_approved_path` without `approved_roots`
- **THEN** the export intent fails validation
