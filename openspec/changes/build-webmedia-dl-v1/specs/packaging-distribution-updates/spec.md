# Delta: packaging-distribution-updates

## ADDED Requirements

### Requirement: Named surfaces

Public names SHALL be WebMedia DL / `webmedia-dl` / `webmedia_dl` / `WebMediaDL`.
`wmdl` SHALL NOT be installed as the canonical console script.

#### Scenario: CLI help uses canonical name

- **WHEN** `webmedia-dl --help` runs
- **THEN** the usage line contains `webmedia-dl`

### Requirement: Reproducible bundle

`scripts/package_bundle.py` SHALL write a zip with a fixed timestamp.
`scripts/validate_bundle.py` SHALL fail if required overlay files or specs are missing.
