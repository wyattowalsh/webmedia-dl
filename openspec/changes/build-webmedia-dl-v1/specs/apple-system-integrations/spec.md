# Delta: apple-system-integrations

## ADDED Requirements

### Requirement: User-approved destinations

Share sheet, Files, and Photos destinations SHALL be user-approved roots. The worker
SHALL NOT silently write into the photo library or arbitrary home paths.

#### Scenario: publication requires approved roots

- **WHEN** `destination_kind` is `user_approved_path` without `approved_roots`
- **THEN** the export intent fails validation

### Requirement: Share and intents adapters

macOS and iOS SHALL expose share-sheet and App Intent adapters that forward locators
to the loopback worker. Those adapters SHALL NOT run provider argv.

#### Scenario: photos without approval
- **WHEN** a share intake has no approved root
- **THEN** `canPublishToPhotos` is false
