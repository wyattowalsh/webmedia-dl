# Delta: discovery-candidates

## ADDED Requirements

### Requirement: Bounded discovery

Discovery SHALL produce `MediaCandidate` nodes from direct URLs or bounded HTML
(size-capped, redirect-capped). It SHALL NOT decide final acquisition.

#### Scenario: HTML extracts media without using the title as identity

- **WHEN** a page contains `og:image`, `video[src]`, and JSON-LD `contentUrl`
- **THEN** candidates exist for those URLs and `identity_key` is not the page title

### Requirement: Candidate graph grouping

Candidates SHALL be grouped by host/identity. Duplicate identities SHALL be recorded
as conflicts. DRM signals SHALL be attached, not stripped.

#### Scenario: Graph records DRM conflicts

- **WHEN** a candidate has DRM signals
- **THEN** the graph `conflicts` list includes a `drm:` entry
