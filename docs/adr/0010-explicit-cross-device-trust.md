---
title: "Pairing is explicit, encrypted, and expiring"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0010: Pairing is explicit, encrypted, and expiring

## Context

WebMedia DL is a local-first universal media acquisition and export system.
This decision records a boundary that the implementation must keep.

## Decision

Pairing is explicit, encrypted, and expiring.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
