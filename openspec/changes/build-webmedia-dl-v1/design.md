# Design

See `docs/planning/build-webmedia-dl-v1/system-architecture.md` for the
recovered architecture. Implementation maps components as follows:

| Component | Module |
|---|---|
| Surface adapters | `cli.py`, `service.py`, `extensions/`, `apps/` |
| Intake | `intake.py` |
| Network policy | `network_policy.py` |
| Discovery | `discovery.py` |
| Candidate graph | `candidates.py` |
| Capability registry | `policy/profiles.py`, `providers.py` |
| Acquisition planner | `acquisition.py` |
| Provider runtime | `providers.py` |
| Artifact store | `artifacts.py` |
| Export planner | `export.py` |
| Processing adapters | `providers.py` (ffmpeg/imagemagick) |
| Validation | `validation.py` |
| Publisher | `publish.py` |
| Queue/event store | `queue.py` |
| Cross-device transport | `transport.py`, `continuity.py`, `envelope.py` |

Control flow is `Pipeline.submit` in `pipeline.py`.
