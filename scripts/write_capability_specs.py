#!/usr/bin/env python3
"""Rewrite OpenSpec capability specs with distinct, testable SHALL requirements."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "openspec/changes/build-webmedia-dl-v1/specs"

BODIES: dict[str, str] = {
    "intake-routing": """
# Delta: intake-routing

## ADDED Requirements

### Requirement: Typed intake without retrieval

Intake SHALL classify and normalize locators into `MediaSource` records. It SHALL NOT
perform network retrieval. `file:` URLs SHALL be rejected as URL intake.

#### Scenario: HTTPS paste

- **WHEN** the CLI receives `https://example.com/a.png`
- **THEN** the source has `normalized_url` set and `local_path` unset

#### Scenario: file scheme rejected

- **WHEN** intake receives `file:///tmp/secret.png` as a URL
- **THEN** it fails closed with `IntakeError`

### Requirement: URL is never a filesystem path

A network locator SHALL NOT be copied into `local_path`.

#### Scenario: URL plus path is invalid

- **WHEN** a `MediaSource` is constructed with both a URL kind and `local_path`
- **THEN** validation fails
""",
    "discovery-candidates": """
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
""",
    "acquisition-adapters": """
# Delta: acquisition-adapters

## ADDED Requirements

### Requirement: Allowlisted provider argv

Provider runtime SHALL build argv only from typed inputs and an allowlist.
Arbitrary `extra_args` SHALL be rejected. Format ids SHALL match `^[A-Za-z0-9+._-]+$`.

#### Scenario: extra_args rejected

- **WHEN** a provider request includes extra argv
- **THEN** `ProviderPolicyError` is raised before any process starts

#### Scenario: yt-dlp format token

- **WHEN** `format_id` is `137+140`
- **THEN** argv contains `--format 137+140` and does not contain `--exec`

### Requirement: No automatic install

Provider manifests SHALL set `install_automatic` false. Missing binaries SHALL be
reported as `BLOCKED` by `doctor`, not silently downloaded.

#### Scenario: doctor does not install yt-dlp

- **WHEN** `yt-dlp` is absent
- **THEN** doctor reports BLOCKED for that provider and does not fetch it
""",
    "asset-store-provenance": """
# Delta: asset-store-provenance

## ADDED Requirements

### Requirement: Content-addressed immutable sources

Source artifacts SHALL be identified as `sha256:<digest>`. After registration, source
bytes SHALL NOT be mutated. Display titles SHALL NOT be used as artifact ids.

#### Scenario: mutate source fails

- **WHEN** code attempts to overwrite a registered source
- **THEN** `ArtifactImmutabilityError` is raised
""",
    "export-planning": """
# Delta: export-planning

## ADDED Requirements

### Requirement: Original is sacred

The default export plan SHALL include an identity copy of the source with
`LossClass.NONE`. Remux SHALL be planned before transcode. Lossy transcode SHALL
require `allow_lossy`.

#### Scenario: default plan keeps original

- **WHEN** intent uses preset `original-sacred`
- **THEN** the plan contains `keep-original` with no loss
""",
    "export-validation-publication": """
# Delta: export-validation-publication

## ADDED Requirements

### Requirement: Mandatory validation before publish

Derivatives and sources SHALL NOT be published to a user-visible destination until
hash and size gates execute with `PASS`. Planned or simulated checks SHALL NOT be
recorded as `PASS`.

#### Scenario: simulated PASS forbidden

- **WHEN** a validation result is constructed with `simulated=true` and `PASS`
- **THEN** `SimulatedPassError` is raised

### Requirement: Transactional destination commit

Publication SHALL write to a temporary directory under an approved root and atomically
replace into the destination. Paths outside approved roots SHALL be denied.

#### Scenario: outside approved root

- **WHEN** destination is not under `approved_roots`
- **THEN** publication fails closed
""",
    "media-processing": """
# Delta: media-processing

## ADDED Requirements

### Requirement: Separate remux and transcode

`process.ffmpeg.remux` SHALL use stream copy. `process.ffmpeg.transcode` SHALL use
allowlisted codecs only. ImageMagick SHALL run with a restrictive policy file and
typed input/output paths.

#### Scenario: remux argv

- **WHEN** remux is requested
- **THEN** argv contains `-c copy` and does not accept user-supplied extra flags
""",
    "live-manifest-recording": """
# Delta: live-manifest-recording

## ADDED Requirements

### Requirement: Clear manifests only

HLS `#EXT-X-KEY` with a method other than `NONE` SHALL be refused. DASH
ContentProtection/cenc SHALL be refused. The product SHALL NOT decrypt or
unwrap DRM.

#### Scenario: AES-128 playlist

- **WHEN** a playlist contains `EXT-X-KEY:METHOD=AES-128`
- **THEN** `DrmRefused` is raised before any segment is fetched
""",
    "queue-events-observability": """
# Delta: queue-events-observability

## ADDED Requirements

### Requirement: Durable local events

Every job SHALL emit typed events to a local store. The queue SHALL NOT expose raw
provider console output as its public API. Default telemetry SHALL be false.

#### Scenario: completed job has events

- **WHEN** `webmedia-dl submit` completes a local file job
- **THEN** `job` JSON includes a non-empty `events` list and no telemetry upload
""",
    "security-privacy-policy": """
# Delta: security-privacy-policy

## ADDED Requirements

### Requirement: No DRM circumvention

Widevine, FairPlay, PlayReady, encrypted HLS, and cenc signals SHALL refuse closed.

### Requirement: Cookie access is explicit

Cookies SHALL require `CookieAccess.EXPLICIT_PATH`, an existing absolute file, and
MUST NOT live inside the repository. Restricted profiles SHALL set cookie access to
`never`.

#### Scenario: repo cookie rejected

- **WHEN** `--cookies` points at a file inside the repo
- **THEN** `CookiePolicyError` is raised

### Requirement: No default telemetry or auto-install

Policy profiles SHALL forbid `telemetry_default` and automatic provider installation.
""",
    "browser-extensions": """
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
""",
    "apple-platform-clients": """
# Delta: apple-platform-clients

## ADDED Requirements

### Requirement: Platform roles

macOS SHALL host the full local worker. iPhone, iPad, and visionOS SHALL be complete
clients that may perform lightweight transfers and MUST pair for heavy work.
watchOS and tvOS SHALL provide capture, status, history, and controls and SHALL NOT
pretend to be subprocess workers.

#### Scenario: watch worker cannot run yt-dlp

- **WHEN** a watchOS worker requests `acquire.ytdlp`
- **THEN** `CapabilityDenied` is raised because `subprocess_capable` is false
""",
    "apple-system-integrations": """
# Delta: apple-system-integrations

## ADDED Requirements

### Requirement: User-approved destinations

Share sheet, Files, and Photos destinations SHALL be user-approved roots. The worker
SHALL NOT silently write into the photo library or arbitrary home paths.

#### Scenario: publication requires approved roots

- **WHEN** `destination_kind` is `user_approved_path` without `approved_roots`
- **THEN** the export intent fails validation
""",
    "cross-device-workers": """
# Delta: cross-device-workers

## ADDED Requirements

### Requirement: Explicit pairing

Pairing SHALL use an expiring nonce. Transport SHALL NOT decide capability policy.
A restricted client SHALL NOT delegate disallowed capabilities to a full worker.

#### Scenario: restricted cannot delegate yt-dlp

- **WHEN** `personal-restricted` asks `personal-full` to run `acquire.ytdlp`
- **THEN** `DelegationDenied` is raised

#### Scenario: consumed envelope nonces expire from the ledger

- **WHEN** a consumed pairing envelope nonce is older than the ledger retention window
- **THEN** the ledger forgets that row so `nonces.sqlite` cannot grow without bound; a later consume of the same nonce is recorded and a replay is denied
""",
    "diagnostics-support": """
# Delta: diagnostics-support

## ADDED Requirements

### Requirement: Evidence-qualified doctor

`webmedia-dl doctor` SHALL report `PASS` / `WARN` / `BLOCKED` / `FAIL` using the
pack legend. Unavailable Apple devices, stores, signing, notarization, App Review,
and legal review SHALL be `BLOCKED`, never `PASS`.

#### Scenario: doctor JSON

- **WHEN** doctor runs on Linux CI
- **THEN** `telemetry_default` is false, `drm_circumvention` is false, and
  `apple_devices.macos.status` is `BLOCKED`
""",
    "accessibility-ux": """
# Delta: accessibility-ux

## ADDED Requirements

### Requirement: Structured expert output, one-tap ordinary path

Ordinary submit SHALL be a single command or extension button. Expert inspection
SHALL be JSON events. Extension UI SHALL include `lang`, a labeled token field,
a keyboard-focusable button, and `aria-live` status.

#### Scenario: capture popup markup

- **WHEN** `extensions/chromium/popup.html` is inspected
- **THEN** it has `html lang`, a `label for="token"`, and `role="status"`
""",
    "migration-compatibility": """
# Delta: migration-compatibility

## ADDED Requirements

### Requirement: Non-destructive legacy scan

`migrate-scan` SHALL detect `yt-dlp-archive.txt` / `archive.txt` markers.
`migrate-apply` SHALL write a sidecar index and SHALL NOT rewrite original archives.

#### Scenario: original archive preserved

- **WHEN** migrate-apply runs on a folder containing `yt-dlp-archive.txt`
- **THEN** the original file bytes are unchanged
""",
    "packaging-distribution-updates": """
# Delta: packaging-distribution-updates

## ADDED Requirements

### Requirement: Named surfaces

Public names SHALL be WebMedia DL / `webmedia-dl` / `webmedia_dl` / `WebMediaDL`.
`wmdl` SHALL NOT be installed as the canonical console script.

#### Scenario: CLI help uses canonical name

- **WHEN** `webmedia-dl --help` runs
- **THEN** the usage line contains `webmedia-dl`

### Requirement: Reproducible bundle

`scripts/package_bundle.py` SHALL write a zip with a fixed timestamp.
`scripts/validate_bundle.py` SHALL fail if required overlay files or specs are missing.
""",
}


def main() -> None:
    for name, body in BODIES.items():
        path = SPECS / name / "spec.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.strip() + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
