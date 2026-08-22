# Delta: apple-system-integrations

## ADDED Requirements

### Requirement: User-approved destinations

Share sheet, Files, and Photos destinations SHALL be user-approved roots. The worker
SHALL NOT silently write into the photo library or arbitrary home paths. Files
destinations SHALL carry a security-scoped bookmark whose path boundary matches
the approved root. Clipboard/paste adapters SHALL extract an http(s) locator and
SHALL NOT copy that locator into `local_path`. PhotoKit library writes SHALL stay
closed until a signed Apple Photos API is available.

#### Scenario: publication requires approved roots

- **WHEN** `destination_kind` is `user_approved_path` without `approved_roots`
- **THEN** the export intent fails validation

#### Scenario: files bookmark path boundary

- **WHEN** a Files destination bookmark is `/Users/me/Movies`
- **THEN** `/Users/me/Movies-backup/clip.mp4` is denied

#### Scenario: clipboard url is not a path

- **WHEN** clipboard text contains `https://cdn.example.com/a.mp4`
- **THEN** intake kind is `paste` and `local_path` is unset

### Requirement: Share and intents adapters

macOS and iOS SHALL expose share-sheet and App Intent adapters that forward locators
to the loopback worker. Those adapters SHALL NOT run provider argv.

#### Scenario: photos without approval
- **WHEN** a share intake has no approved root
- **THEN** `canPublishToPhotos` is false

#### Scenario: share sheet url versus file
- **WHEN** a share sheet supplies `https://example.com/a.mp4` and `file:///tmp/a.png`
- **THEN** the HTTPS value is URL intake and the file URL is drop intake

#### Scenario: complete clients carry files destinations
- **WHEN** iPhone, iPad, or visionOS submit with an approved Files path
- **THEN** the job intent uses `files_app` and the security-scoped path boundary

#### Scenario: share destination publishes under approved root

- **WHEN** `destination_kind` is `share` under an approved root
- **THEN** publication writes under that root and Photos library writes stay closed
