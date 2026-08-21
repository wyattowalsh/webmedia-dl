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

### Requirement: Paired Mac confirmation

Heavy work from iPhone, iPad, or visionOS SHALL run on the Mac worker only after an
expiring pairing nonce is confirmed by the Mac user. Unconfirmed pairing SHALL NOT
change the client profile to `personal-full`.

#### Scenario: unconfirmed pairing
- **WHEN** an iOS job supplies a pairing id that has not been confirmed
- **THEN** `DelegationDenied` is raised and yt-dlp is not executed
