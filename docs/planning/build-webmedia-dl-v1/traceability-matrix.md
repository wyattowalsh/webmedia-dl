---
title: "Traceability matrix"
status: proposed
type: planning
change: build-webmedia-dl-v1
last_reviewed: 2026-08-18
---
# Traceability matrix

Maps recovered architecture invariants and OpenSpec capabilities to executed tests.
Original pack SHALL text remains unverified until the 2026-08-18 ZIP is re-attached.

| Requirement | Evidence |
|---|---|
| URL ≠ path | `tests/unit/webmedia_dl/test_invariants.py` |
| Title ≠ identity | `tests/unit/webmedia_dl/test_invariants.py` |
| No user argv | `tests/unit/webmedia_dl/test_providers.py` |
| Immutable source | `tests/unit/webmedia_dl/test_invariants.py` |
| Validation before publish | `tests/unit/webmedia_dl/test_validation_publish.py` |
| No profile escalation | `tests/unit/webmedia_dl/test_policy.py` |
| No simulated PASS | `tests/unit/webmedia_dl/test_invariants.py` |
| DRM refused | `tests/unit/webmedia_dl/test_security.py`, `tests/unit/webmedia_dl/test_live.py`, `tests/unit/webmedia_dl/test_openspec_shall_gaps.py` |
| Loopback auth | `tests/unit/webmedia_dl/test_service.py` |
| Typed intake | `tests/unit/webmedia_dl/test_intake.py` |
| Bounded discovery | `tests/unit/webmedia_dl/test_discovery.py` |
| Browser evidence / srcset | `tests/unit/webmedia_dl/test_plan_evidence_replay.py` |
| Manifest dump-json | `tests/unit/webmedia_dl/test_queue_manifest.py` |
| Queue pause | `tests/unit/webmedia_dl/test_queue_manifest.py` |
| Envelope replay | `tests/unit/webmedia_dl/test_plan_evidence_replay.py` |
| Cookie policy | `tests/unit/webmedia_dl/test_security.py`, `tests/unit/webmedia_dl/test_queue_manifest.py` |
| Extension capture only | `tests/unit/extensions/capture.test.mjs` |
| Apple shells | `tests/unit/webmedia_dl/test_surfaces_inventory.py` |
| Swift schema keys | `tests/unit/webmedia_dl/test_swift_schema_parity.py` |
| OpenSpec scenarios | `openspec/.../specs/*/spec.md` | `test_openspec_shall_gaps.py` WHEN/THEN + named-test map |

| Capability | Spec | Tests |
|---|---|---|
| accessibility-ux | `openspec/.../accessibility-ux/spec.md` | `test_accessibility_markup.py` |
| acquisition-adapters | `openspec/.../acquisition-adapters/spec.md` | `test_providers.py`, `test_openspec_shall_gaps.py` |
| apple-platform-clients | `openspec/.../apple-platform-clients/spec.md` | `test_surfaces_inventory.py`, `test_pairing_surfaces.py`, `test_openspec_shall_gaps.py`, `test_fail_closed_followups.py` |
| apple-system-integrations | `openspec/.../apple-system-integrations/spec.md` | Share/intent files + `IdentityTests.swift` + `test_openspec_shall_gaps.py` |
| asset-store-provenance | `openspec/.../asset-store-provenance/spec.md` | `test_invariants.py` |
| browser-extensions | `openspec/.../browser-extensions/spec.md` | `capture.test.mjs` |
| cross-device-workers | `openspec/.../cross-device-workers/spec.md` | `test_pairing_surfaces.py`, `test_openspec_shall_gaps.py` |
| diagnostics-support | `openspec/.../diagnostics-support/spec.md` | `test_cli.py` doctor, `test_openspec_shall_gaps.py` |
| discovery-candidates | `openspec/.../discovery-candidates/spec.md` | `test_discovery.py`, `test_candidates.py`, `test_openspec_shall_gaps.py` |
| export-planning | `openspec/.../export-planning/spec.md` | `test_coverage_gaps.py`, `test_fail_closed_followups.py` |
| export-validation-publication | `openspec/.../export-validation-publication/spec.md` | `test_validation_publish.py`, `test_fail_closed_followups.py` |
| intake-routing | `openspec/.../intake-routing/spec.md` | `test_intake.py` |
| live-manifest-recording | `openspec/.../live-manifest-recording/spec.md` | `test_live.py`, `test_p2_contracts.py`, `test_openspec_shall_gaps.py`, `test_fail_closed_followups.py` |
| media-processing | `openspec/.../media-processing/spec.md` | `test_processing.py` |
| migration-compatibility | `openspec/.../migration-compatibility/spec.md` | `test_compat_transport.py` |
| packaging-distribution-updates | `openspec/.../packaging-distribution-updates/spec.md` | `test_names.py`, `validate_bundle.py`, `test_openspec_shall_gaps.py` |
| queue-events-observability | `openspec/.../queue-events-observability/spec.md` | `test_cli_e2e.py`, `test_queue_manifest.py`, `test_openspec_shall_gaps.py`, `test_fail_closed_followups.py` |
| security-privacy-policy | `openspec/.../security-privacy-policy/spec.md` | `test_security.py`, `test_policy.py`, `test_openspec_shall_gaps.py` |
