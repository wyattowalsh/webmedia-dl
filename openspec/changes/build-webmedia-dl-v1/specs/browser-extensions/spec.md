# Delta: browser-extensions

## ADDED Requirements

### Requirement: Evidence capture only

Safari, Chrome, Brave, Edge, generic Chromium, and Firefox extensions SHALL collect
page media URLs and POST them to the loopback worker. They SHALL NOT expose a generic
native command runner. `javascript:` URLs SHALL be ignored.

#### Scenario: collector returns no native command

- **WHEN** `collectMediaEvidence` runs on a document with video and `javascript:` img
- **THEN** `nativeCommand` is null and the javascript URL is omitted

### Requirement: Loopback only

Host permissions SHALL be limited to `http://127.0.0.1:8765/*`.

#### Scenario: each engine has a capture tree

- **WHEN** `extensions/{safari,chrome,brave,edge,chromium,firefox}/manifest.json` is read
- **THEN** each file lists only the loopback host permission
