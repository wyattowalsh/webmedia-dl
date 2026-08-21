# Delta: export-planning

## ADDED Requirements

### Requirement: export planning follows the shared typed model

The `export-planning` surface SHALL use the shared job, event, capability, policy,
artifact, and export model. It SHALL NOT introduce a parallel identity scheme
based on display titles or source URLs-as-paths.

#### Scenario: Contracts are schema-valid

- **WHEN** a `export-planning` payload is produced
- **THEN** it validates against the corresponding JSON Schema in `schemas/`

### Requirement: Policy and evidence gates

`export-planning` SHALL honor client and worker policy profiles, SHALL refuse DRM
circumvention, SHALL NOT enable default telemetry, and SHALL record evidence
statuses using only `PASS`, `WARN`, `BLOCKED`, or `FAIL`.

#### Scenario: Simulated checks stay non-PASS

- **WHEN** a check is planned or simulated and has not executed
- **THEN** its status is not `PASS`

### Requirement: Failure containment

Failures in `export-planning` SHALL write only to staging or durable queue state
until publication. One derivative failure SHALL NOT invalidate unrelated
artifacts.

#### Scenario: Partial failure is quarantined

- **WHEN** an operation fails
- **THEN** partial bytes land in quarantine or remain unpublished
