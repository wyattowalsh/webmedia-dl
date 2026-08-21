# Delta: export-validation-publication

## ADDED Requirements

### Requirement: Mandatory validation before publish

Derivatives and sources SHALL NOT be published to a user-visible destination until
hash and size gates execute with `PASS`. Planned or simulated checks SHALL NOT be
recorded as `PASS`.

#### Scenario: simulated PASS forbidden

- **WHEN** a validation result is constructed with `simulated=true` and `PASS`
- **THEN** `SimulatedPassError` is raised

### Requirement: Transactional destination commit

Publication SHALL write to a temporary directory under an approved root and atomically
replace into the destination. Paths outside approved roots SHALL be denied.

#### Scenario: outside approved root

- **WHEN** destination is not under `approved_roots`
- **THEN** publication fails closed
