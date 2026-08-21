---
title: "Start here: WebMedia DL final planning pack"
status: final-planning
type: navigation
change: build-webmedia-dl-v1
last_reviewed: 2026-08-18
load_when: "Beginning review or implementation planning."
---
# WebMedia DL final planning pack

> [!important] Planning status
> This is a **final planning and specification release**, not an implemented or production-ready application. The active OpenSpec change is `build-webmedia-dl-v1` and remains **proposed**.

> [!warning] Prior-bundle evidence boundary
> The previously described planning directory and ZIP were not available in the active workspace or File Library. `AUDIT_REPORT.md` therefore distinguishes the surviving command and documented decisions from reconstructed critique of the absent bundle. No prior-byte comparison is claimed.

## What this pack decides

- Product name: **WebMedia DL**.
- Repository and CLI: **`webmedia-dl`**.
- `wmdl`: optional personal alias only, not the public canonical name.
- macOS: full local worker and native app.
- iPhone, iPad, and visionOS: complete clients with direct lightweight transfers and paired-Mac execution for complex work.
- watchOS and tvOS: platform-appropriate capture, status, history, and controls, not fictional subprocess workers.
- Safari, Chrome, Brave, Edge, generic Chromium, and Firefox capture extensions in v1.
- One typed job, event, capability, policy, artifact, and export model across every surface.
- Immutable sources, least-destructive conversion, semantic parity, layered validation, and transactional publication.
- No mandatory cloud backend, default telemetry, DRM circumvention, automatic provider installation, or silent cookie access.

## Read in this order

1. [`START_HERE.md`](START_HERE.md)
2. [`README.md`](README.md)
3. [`docs/maps/build-webmedia-dl-v1-moc.md`](docs/maps/build-webmedia-dl-v1-moc.md)
4. [`AUDIT_REPORT.md`](AUDIT_REPORT.md)
5. [`openspec/changes/build-webmedia-dl-v1/proposal.md`](openspec/changes/build-webmedia-dl-v1/proposal.md)
6. `openspec/changes/build-webmedia-dl-v1/specs/`
7. [`openspec/changes/build-webmedia-dl-v1/design.md`](openspec/changes/build-webmedia-dl-v1/design.md)
8. [`openspec/changes/build-webmedia-dl-v1/tasks.md`](openspec/changes/build-webmedia-dl-v1/tasks.md)
9. [`docs/planning/build-webmedia-dl-v1/traceability-matrix.md`](docs/planning/build-webmedia-dl-v1/traceability-matrix.md)
10. [`docs/planning/build-webmedia-dl-v1/validation.md`](docs/planning/build-webmedia-dl-v1/validation.md)
11. [`docs/planning/build-webmedia-dl-v1/codex-handoff.md`](docs/planning/build-webmedia-dl-v1/codex-handoff.md)
12. [`guide/index.html`](guide/index.html)

## Architecture in one view

```mermaid
flowchart LR
    U[Share, paste, drop, browser, intent, CLI] --> I[Typed intake]
    I --> D[Bounded discovery]
    D --> C[Candidate graph]
    C --> R[Policy and capability routing]
    R --> A[Acquisition]
    A --> S[Immutable source]
    S --> P[Loss-aware export plan]
    P --> O[Operation DAG]
    O --> V[Validation]
    V --> T[Transactional publish]
    T --> Q[Queue, history, provenance]
```

## Evidence legend

| Status | Meaning |
|---|---|
| `PASS` | The stated check executed and satisfied its gate. |
| `WARN` | A non-blocking concern remains with owner/recheck. |
| `BLOCKED` | A runtime, account, device, source, approval, or tool is unavailable. |
| `FAIL` | The gate was executed and violated. |

Planning structure, schemas, links, task DAG, traceability, HTML, archive safety, clean extraction, and reproducible ZIP checks are executed in this bundle. Product runtime, Apple devices, installed providers, browser stores, signing, notarization, App Review, and human legal review remain `BLOCKED` until implementation.

## Fast paths

- **Product decision:** `docs/planning/build-webmedia-dl-v1/product-brief.md`
- **Reconstructed audit:** `AUDIT_REPORT.md`
- **Behavior:** `openspec/changes/build-webmedia-dl-v1/specs/`
- **Architecture:** `openspec/changes/build-webmedia-dl-v1/design.md`
- **Build order:** `openspec/changes/build-webmedia-dl-v1/tasks.md`
- **Optimization/export:** `docs/planning/build-webmedia-dl-v1/optimization-conversion-export.md`
- **Apple:** `docs/planning/build-webmedia-dl-v1/apple-platforms.md`
- **Browser extensions:** `docs/planning/build-webmedia-dl-v1/browser-extensions.md`
- **Security:** `docs/planning/build-webmedia-dl-v1/security-threat-model.md`
- **Interactive guide:** `guide/index.html`
