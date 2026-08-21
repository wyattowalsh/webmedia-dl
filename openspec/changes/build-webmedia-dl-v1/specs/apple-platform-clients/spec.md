# Delta: apple-platform-clients

## ADDED Requirements

### Requirement: Platform roles

macOS SHALL host the full local worker. iPhone, iPad, and visionOS SHALL be complete
clients that may perform lightweight transfers and MUST pair for heavy work.
watchOS and tvOS SHALL send typed companion messages (`capture`, `pause`,
`resume`, `history`, `status`, `cancel`) to the Mac. Those messages SHALL set
`nativeCommand` to null and SHALL NOT carry provider argv. The Mac worker
`POST /v1/companion` SHALL accept them only from the Mac actor and MAY mark the
job host-owned so heavy work runs on the Mac without granting the watch a
subprocess runtime.

#### Scenario: companion capture has no native command

- **WHEN** a watch companion message is built for capture
- **THEN** `nativeCommand` is null and `subprocessWorker` is false

#### Scenario: watch worker cannot run yt-dlp

- **WHEN** a watchOS worker requests `acquire.ytdlp`
- **THEN** `CapabilityDenied` is raised because `subprocess_capable` is false

#### Scenario: watch queues for Mac relay

- **WHEN** watchOS or tvOS captures a URL
- **THEN** the companion message is queued for Mac relay with `nativeCommand`
  null and `subprocessWorker` false, and those surfaces do not open yt-dlp

### Requirement: Paired Mac confirmation

Heavy work from iPhone, iPad, or visionOS SHALL run on the Mac worker only after an
expiring pairing nonce is confirmed by the Mac user. Unconfirmed pairing SHALL NOT
change the client profile to `personal-full`.

#### Scenario: unconfirmed pairing
- **WHEN** an iOS job supplies a pairing id that has not been confirmed
- **THEN** `DelegationDenied` is raised and yt-dlp is not executed
