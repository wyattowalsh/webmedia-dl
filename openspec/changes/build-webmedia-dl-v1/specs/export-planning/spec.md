# Delta: export-planning

## ADDED Requirements

### Requirement: Original is sacred

The default export plan SHALL include an identity copy of the source with
`LossClass.NONE`. Remux SHALL be planned before transcode. Lossy transcode SHALL
require `allow_lossy`.

#### Scenario: default plan keeps original

- **WHEN** intent uses preset `original-sacred`
- **THEN** the plan contains `keep-original` with no loss

#### Scenario: remux is planned before transcode

- **WHEN** intent sets `allow_lossy` and a remux container
- **THEN** the plan lists `remux` before `transcode`, and without `allow_lossy` there is no transcode
