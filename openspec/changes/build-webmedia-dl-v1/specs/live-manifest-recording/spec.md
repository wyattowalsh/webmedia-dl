# Delta: live-manifest-recording

## ADDED Requirements

### Requirement: Clear manifests only

HLS `#EXT-X-KEY` with a method other than `NONE` SHALL be refused. DASH
ContentProtection/cenc SHALL be refused. The product SHALL NOT decrypt or
unwrap DRM.

#### Scenario: AES-128 playlist

- **WHEN** a playlist contains `EXT-X-KEY:METHOD=AES-128`
- **THEN** `DrmRefused` is raised before any segment is fetched
