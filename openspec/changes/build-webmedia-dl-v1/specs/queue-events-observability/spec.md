# Delta: queue-events-observability

## ADDED Requirements

### Requirement: Durable local events

Every job SHALL emit typed events to a local store. The queue SHALL NOT expose raw
provider console output as its public API. Default telemetry SHALL be false.

#### Scenario: completed job has events

- **WHEN** `webmedia-dl submit` completes a local file job
- **THEN** `job` JSON includes a non-empty `events` list and no telemetry upload
