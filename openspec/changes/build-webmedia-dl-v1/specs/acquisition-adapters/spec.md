# Delta: acquisition-adapters

## ADDED Requirements

### Requirement: Allowlisted provider argv

Provider runtime SHALL build argv only from typed inputs and an allowlist.
Arbitrary `extra_args` SHALL be rejected. Format ids SHALL match `^[A-Za-z0-9+._-]+$`.

#### Scenario: extra_args rejected

- **WHEN** a provider request includes extra argv
- **THEN** `ProviderPolicyError` is raised before any process starts

#### Scenario: yt-dlp format token

- **WHEN** `format_id` is `137+140`
- **THEN** argv contains `--format 137+140` and does not contain `--exec`

### Requirement: No automatic install

Provider manifests SHALL set `install_automatic` false. Missing binaries SHALL be
reported as `BLOCKED` by `doctor`, not silently downloaded.

#### Scenario: doctor does not install yt-dlp

- **WHEN** `yt-dlp` is absent
- **THEN** doctor reports BLOCKED for that provider and does not fetch it
