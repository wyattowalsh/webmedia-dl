---
title: "Implementation plan"
status: proposed
type: planning
change: build-webmedia-dl-v1
last_reviewed: 2026-08-18
---
# Implementation plan

Python worker first in this repository. Apple UI, signing, stores, and App Review remain hardware-gated.

## Order

1. Shared domain model, schemas, invariants.
2. Intake, network policy, bounded discovery, candidate graph.
3. Capability registry, policy profiles, acquisition planner, provider argv allowlists.
4. Artifact store, export planner, ffmpeg/ImageMagick processing, validation, transactional publish.
5. Queue/events, CLI, loopback worker API, pairing envelopes.
6. Browser capture extensions (Safari/Chromium/Firefox families).
7. Swift packages and share/intent/continuity shells for Apple surfaces.
8. Release gates: signing, notarization, store submission, legal review (`BLOCKED` until executed).

## Worker runtime

`Pipeline.submit` enqueues a typed job and, unless `--no-wait` or a queue pause is set, runs intake → discovery → plan → acquire → validate → publish. `webmedia-dl plan` explains ranked strategies without acquiring. `webmedia-dl serve` starts the loopback API and a queue dispatcher. Restricted profiles cannot delegate disallowed capabilities. Pairing envelopes use AES-GCM.
