---
title: "Planning artifacts stay plain-text and schema-backed"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0015: Planning artifacts stay plain-text and schema-backed

## Context

WebMedia DL is a local-first universal media acquisition and export system.
This decision records a boundary that the implementation must keep.

## Decision

Planning artifacts stay plain-text and schema-backed.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
