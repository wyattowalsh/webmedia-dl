# Delta: export-planning

## ADDED Requirements

### Requirement: Original is sacred

The default export plan SHALL include an identity copy of the source with
`LossClass.NONE`. Remux SHALL be planned before transcode. Lossy transcode SHALL
require `allow_lossy`.

#### Scenario: default plan keeps original

- **WHEN** intent uses preset `original-sacred`
- **THEN** the plan contains `keep-original` with no loss
