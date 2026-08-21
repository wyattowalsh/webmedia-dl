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
Clear DASH `SegmentList` `Initialization`/`SegmentURL` ranges SHALL be sliced
from the fetched object (`start-end` inclusive) rather than concatenated as
whole files. `AdaptationSet` BaseURL and `SegmentTemplate` values SHALL bind
child `Representation` identifiers, including self-closing representations.
Dynamic MPDs (`type="dynamic"`) and HLS playlists without `#EXT-X-ENDLIST`
SHALL be polled for newly advertised segments under the profile byte bound.

#### Scenario: two clear transport segments

- **WHEN** a playlist lists `seg1.ts` and `seg2.ts` with no encryption
- **THEN** the recorded source bytes are the concatenation of both segments

#### Scenario: DASH SegmentList byte ranges

- **WHEN** an MPD lists one media object with `range` / `mediaRange`
- **THEN** the recorded source bytes are the concatenated slices, not the whole file

#### Scenario: AdaptationSet binds Representation identifiers

- **WHEN** an AdaptationSet supplies BaseURL and SegmentTemplate and a
  self-closing Representation declares `id="v1"`
- **THEN** the recorded locator is the AdaptationSet BaseURL plus `v1` plus the
  template media path

#### Scenario: dynamic MPD polling

- **WHEN** a dynamic MPD later advertises an additional segment
- **THEN** recording concatenates only newly advertised parts and stops if
  ContentProtection appears
