---
title: "Domain model"
status: proposed
type: planning
change: build-webmedia-dl-v1
last_reviewed: 2026-08-18
---
# Domain model

Canonical types live in `src/webmedia_dl/domain/models.py` and are exported to `schemas/`.
Swift Core mirrors the same JSON keys in `apps/WebMediaDLCore/Sources/WebMediaDLCore/Domain.swift`.

| Type | Role |
|---|---|
| `MediaSource` | Typed intake. A URL never becomes `local_path`. |
| `MediaCandidate` | Discovery node. `identity_key` is never a display title. |
| `CandidateGraph` | Grouping, alternatives, DRM conflicts. |
| `Job` | One typed job across every surface. |
| `PolicyProfile` / `Worker` | Capability intersection. No privilege escalation. |
| `AcquisitionPlan` / `ExportPlan` | Ranked strategies and least-destructive DAG. |
| `Artifact` | Content-addressed `sha256:…`. Sources immutable. |
| `ValidationResult` | PASS requires executed, non-simulated checks. |
| `EventRecord` | Durable local lifecycle. Not provider console output. |
