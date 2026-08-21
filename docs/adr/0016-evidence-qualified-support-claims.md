---
title: "PASS requires executed evidence"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0016: PASS requires executed evidence

## Context

WebMedia DL is a local-first universal media acquisition and export system.
This decision records a boundary that the implementation must keep.

## Decision

PASS requires executed evidence.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
