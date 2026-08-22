# Delta: acquisition-adapters

## ADDED Requirements

### Requirement: Allowlisted provider argv

Provider runtime SHALL build argv only from typed inputs and an allowlist.
Arbitrary `extra_args` SHALL be rejected. Format ids SHALL match
`^[A-Za-z0-9+._][A-Za-z0-9+._-]*$`.

#### Scenario: extra_args rejected

- **WHEN** a provider request includes extra argv
- **THEN** `ProviderPolicyError` is raised before any process starts

#### Scenario: yt-dlp format token

- **WHEN** `format_id` is `137+140`
- **THEN** argv contains `--format 137+140` and does not contain `--exec`

#### Scenario: unsafe format id is rejected

- **WHEN** `format_id` is `--cookies` or `-best`
- **THEN** the format id is refused and yt-dlp is not executed

#### Scenario: every provider argv is allowlisted

- **WHEN** a shipped provider builds argv from typed inputs
- **THEN** every flag is on that provider's allowlist

### Requirement: No automatic install

Provider manifests SHALL set `install_automatic` false. Missing binaries SHALL be
reported as `BLOCKED` by `doctor`, not silently downloaded.

#### Scenario: doctor does not install yt-dlp

- **WHEN** `yt-dlp` is absent
- **THEN** doctor reports BLOCKED for that provider and does not fetch it

#### Scenario: shipped providers never auto-install

- **WHEN** builtin provider manifests are loaded
- **THEN** `install_automatic` is false and `accepts_user_argv` is false

#### Scenario: missing provider binary is not healthy

- **WHEN** a resolved provider path does not exist
- **THEN** capability health is `missing`, not `healthy`

### Requirement: HTTP-direct is only for direct media locators

`acquire.http` SHALL be planned only when the retrieval URL itself names a media
object. Watch pages discovered via `discover.manifest` SHALL use `acquire.ytdlp`.

#### Scenario: YouTube watch page is not fetched as HTTP bytes

- **WHEN** a candidate's retrieval URL has no media extension
- **THEN** the ranked plan SHALL NOT include `http-direct` for that URL
