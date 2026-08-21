        ---
        title: "Traceability matrix"
        status: proposed
        type: planning
        change: build-webmedia-dl-v1
        last_reviewed: 2026-08-18
        ---
        # Traceability matrix

        | Requirement | Evidence |
|---|---|
| URL ≠ path | `test_invariants.py` |
| Title ≠ identity | `test_invariants.py` |
| No user argv | `test_providers.py` |
| Immutable source | `test_invariants.py` |
| Validation before publish | `test_validation_publish.py` |
| No profile escalation | `test_policy.py` |
| No simulated PASS | `test_invariants.py` |
| DRM refused | `test_security.py` |
| Loopback auth | `test_service.py` |

