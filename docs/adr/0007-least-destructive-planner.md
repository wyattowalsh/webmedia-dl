---
title: "Export planning prefers zero-loss operations"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0007: Export planning prefers zero-loss operations

## Context

WebMedia DL is a local-first universal media acquisition and export system.
This decision records a boundary that the implementation must keep.

## Decision

Export planning prefers zero-loss operations.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
