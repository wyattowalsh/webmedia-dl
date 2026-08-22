# Delta: discovery-candidates

## ADDED Requirements

### Requirement: Bounded discovery

Discovery SHALL produce `MediaCandidate` nodes from direct URLs or bounded HTML
(size-capped, redirect-capped). It SHALL NOT decide final acquisition.
Mixed-media pages SHALL keep one preferred candidate per media kind.
HTML discovery SHALL include `track[src]` subtitles and `a[href]` locators that
name a direct media or document object. Non-media anchors SHALL be ignored.
HTML discovery SHALL also collect `iframe`/`embed`/`object` locators, `link`
preload media, Open Graph `og:video:secure_url` / `og:audio:secure_url`, and
JSON-LD `@type` when the locator has no media extension.

#### Scenario: HTML extracts media without using the title as identity

- **WHEN** a page contains `og:image`, `video[src]`, and JSON-LD `contentUrl`
- **THEN** candidates exist for those URLs and `identity_key` is not the page title

#### Scenario: track and media anchors

- **WHEN** a page contains `track[src]` and an `a[href]` to a PDF
- **THEN** subtitle and document candidates exist and `/about` is ignored

#### Scenario: iframe, preload link, and JSON-LD type

- **WHEN** a page contains an `iframe` to an `.m3u8`, a preload video `link`, and
  JSON-LD `VideoObject.embedUrl` without a media extension
- **THEN** live-stream, video, and typed JSON-LD video candidates exist

#### Scenario: amp-img and twitter player

- **WHEN** a page contains `amp-img[src]` and `twitter:player`
- **THEN** image and video candidates exist for those locators

#### Scenario: HTML discovery is size capped

- **WHEN** HTML discovery exceeds the profile byte cap
- **THEN** fetching stops at the cap and discovery continues on the truncated page

#### Scenario: fetch redirects are bounded

- **WHEN** a discovery fetch exceeds the profile redirect bound
- **THEN** the fetch fails closed

#### Scenario: discovery does not select acquisition

- **WHEN** discovery modules are imported
- **THEN** they do not import acquisition planners or provider execution

### Requirement: Candidate graph grouping

Candidates SHALL be grouped by host/identity. Duplicate identities SHALL be recorded
as conflicts. DRM signals SHALL be attached, not stripped.

#### Scenario: Graph records DRM conflicts

- **WHEN** a candidate has DRM signals
- **THEN** the graph `conflicts` list includes a `drm:` entry
