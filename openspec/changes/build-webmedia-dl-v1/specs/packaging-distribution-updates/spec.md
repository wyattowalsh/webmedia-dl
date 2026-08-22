# Delta: packaging-distribution-updates

## ADDED Requirements

### Requirement: Named surfaces

Public names SHALL be WebMedia DL / `webmedia-dl` / `webmedia_dl` / `WebMediaDL`.
`wmdl` SHALL NOT be installed as the canonical console script.

#### Scenario: CLI help uses canonical name

- **WHEN** `webmedia-dl --help` runs
- **THEN** the usage line contains `webmedia-dl`

#### Scenario: wmdl is not the console script

- **WHEN** the packaged wheel is installed in an isolated venv
- **THEN** `wmdl` is not a console script and help usage is `webmedia-dl`

### Requirement: Reproducible bundle

`scripts/package_bundle.py` SHALL write a zip with a fixed timestamp.
`scripts/validate_bundle.py` SHALL fail if required overlay files or specs are missing.

#### Scenario: bundle zip uses a fixed timestamp

- **WHEN** `scripts/package_bundle.py` writes an archive
- **THEN** every zip member timestamp is `2026-08-18 00:00:00`
