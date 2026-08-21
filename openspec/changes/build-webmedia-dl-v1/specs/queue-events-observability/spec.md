# Delta: queue-events-observability

## ADDED Requirements

### Requirement: Durable local events

Every job SHALL emit typed events to a local store. The queue SHALL NOT expose raw
provider console output as its public API. Default telemetry SHALL be false.
Event payloads SHALL reject `stdout`, `stderr`, `argv`, `nativeCommand`,
`providerArgv`, and cookie file paths.

#### Scenario: completed job has events

- **WHEN** `webmedia-dl submit` completes a local file job
- **THEN** stdout JSON includes a `job` object and a non-empty `events` list and no telemetry upload

#### Scenario: event payload is not a provider console

- **WHEN** code constructs an `EventRecord` with `stdout` in the payload
- **THEN** validation fails closed

### Requirement: Queue pause SHALL prevent starting the next job

The system SHALL persist a queue-level pause flag. While paused, `next_runnable`
SHALL return nothing and workers SHALL NOT start a new job. Resume SHALL clear
the flag. Per-job pause SHALL set job state to `PAUSED` and SHALL NOT be started
by queue resume. `run_next` SHALL restore HTML, cookie path, and browser evidence
from the job context store. Queue-level events SHALL use a well-known zero UUID.
The queue SHALL persist a per-job checkpoint of acquired source artifact ids and
kinds. In-flight `pause_job` SHALL stop before the next stage, keep already
registered sources, and `resume_job` SHALL skip kinds already acquired.

#### Scenario: Queue is paused

- **WHEN** the operator pauses the queue
- **THEN** a newly submitted job SHALL remain `accepted` until resume and `run-next`

#### Scenario: Per-job pause is distinct from queue pause

- **WHEN** a job is paused
- **THEN** `run_next` SHALL skip it until `resume_job`

#### Scenario: Pause mid-acquire keeps registered sources

- **WHEN** a mixed-media job is paused after the first kind is registered
- **THEN** the job state is `PAUSED`, the checkpoint lists that source, and resume
  acquires remaining kinds without deleting the first source
