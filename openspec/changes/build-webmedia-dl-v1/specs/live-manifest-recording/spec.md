# Delta: live-manifest-recording

## ADDED Requirements

### Requirement: Clear manifests only

HLS `#EXT-X-KEY` with a method other than `NONE` SHALL be refused. DASH
ContentProtection/cenc SHALL be refused. The product SHALL NOT decrypt or
unwrap DRM.

#### Scenario: AES-128 playlist

- **WHEN** a playlist contains `EXT-X-KEY:METHOD=AES-128`
- **THEN** `DrmRefused` is raised before any segment is fetched

### Requirement: Concatenate clear segments

Clear HLS (and nested media playlists referenced by a master playlist) SHALL be
fetched under the profile byte bound and concatenated into an immutable source
artifact. Recording SHALL stop before any encrypted key line is processed.

#### Scenario: two clear transport segments

- **WHEN** a playlist lists `seg1.ts` and `seg2.ts` with no encryption
- **THEN** the recorded source bytes are the concatenation of both segments
