---
title: "Python worker, Swift clients, JS extensions"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0003: Python worker, Swift clients, JS extensions

## Context

WebMedia DL is a local-first universal media acquisition and export system
for Apple devices and desktop browsers. This record is derived from the
recovered 2026-08-18 architecture and product brief.

## Decision

The worker and CLI are Python. Apple clients are Swift. Browser capture is JavaScript. Surface adapters MUST NOT own provider argv or policy bypass.

The implementation SHALL keep these architecture invariants:
- A source URL never becomes a filesystem path.
- A display title never becomes artifact identity.
- A provider never receives arbitrary user arguments.
- A source artifact is never mutated after registration.
- A derivative never publishes before mandatory validation.
- A worker never executes a capability denied by client or worker profile.
- A restricted profile never delegates disallowed work to a more capable worker.
- A browser extension never becomes a generic native command runner.
- A planned or simulated check never becomes runtime PASS.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
