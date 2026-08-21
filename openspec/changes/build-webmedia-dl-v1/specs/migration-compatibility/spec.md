# Delta: migration-compatibility

## ADDED Requirements

### Requirement: Non-destructive legacy scan

`migrate-scan` SHALL detect `yt-dlp-archive.txt` / `archive.txt` markers.
`migrate-apply` SHALL write a sidecar index and SHALL NOT rewrite original archives.

#### Scenario: original archive preserved

- **WHEN** migrate-apply runs on a folder containing `yt-dlp-archive.txt`
- **THEN** the original file bytes are unchanged
