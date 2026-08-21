---
title: "Extensions capture evidence, not native argv"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0011: Extensions capture evidence, not native argv

## Context

WebMedia DL is a local-first universal media acquisition and export system.
This decision records a boundary that the implementation must keep.

## Decision

Extensions capture evidence, not native argv.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
