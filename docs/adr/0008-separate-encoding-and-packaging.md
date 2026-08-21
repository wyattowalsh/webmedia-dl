---
title: "Remux is not transcode"
status: accepted
date: 2026-08-18
change: build-webmedia-dl-v1
---
# ADR 0008: Remux is not transcode

## Context

WebMedia DL is a local-first universal media acquisition and export system.
This decision records a boundary that the implementation must keep.

## Decision

Remux is not transcode.

## Consequences

- Tests under `tests/` encode the decision as an invariant or contract.
- Violations fail closed with a typed error rather than silent fallback.
