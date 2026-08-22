# Delta: apple-platform-clients

## ADDED Requirements

### Requirement: Platform roles

macOS SHALL host the full local worker. iPhone, iPad, and visionOS SHALL be complete
clients that may perform lightweight transfers and MUST pair for heavy work.
watchOS and tvOS SHALL send typed companion messages (`capture`, `pause`,
`resume`, `history`, `status`, `cancel`, `pause_job`, `resume_job`) to the Mac.
Those messages SHALL set
`nativeCommand` to null and SHALL NOT carry provider argv. Cancel, pause_job,
and resume_job SHALL include a job UUID. The Mac worker
`POST /v1/companion` SHALL accept them only from the Mac actor and MAY mark the
job host-owned so heavy work runs on the Mac without granting the watch a
subprocess runtime.

#### Scenario: macos hosts the full local worker

- **WHEN** the default worker for macOS is constructed
- **THEN** it uses `personal-full`, is subprocess capable, and allows yt-dlp,
  gallery-dl, ffmpeg remux, and clear live recording

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

#### Scenario: watch control intents queue companion kinds

- **WHEN** watchOS or tvOS Siri/Shortcuts pause, resume, history, status, cancel,
  or pause/resume a job
- **THEN** each action queues the matching companion kind with `nativeCommand`
  null, and cancel/pause_job/resume_job include a UUID `job_id`

#### Scenario: tvOS uses local-network companion transport

- **WHEN** tvOS sends a companion message
- **THEN** it uses a saved Mac LAN relay rather than WatchConnectivity

#### Scenario: iPhone forwards watch companion messages

- **WHEN** the iPhone companion app receives a WatchConnectivity companion message
- **THEN** it forwards that typed message to the paired Mac relay

#### Scenario: sealed companion envelope

- **WHEN** the Mac worker receives a companion POST with AES-GCM envelope fields
  and a confirmed pairing
- **THEN** it opens the envelope once, rejects replay, and still refuses
  `nativeCommand`

#### Scenario: companion endpoint requires the mac actor

- **WHEN** a non-Mac actor POSTs `/v1/companion`
- **THEN** the worker refuses the request

### Requirement: Paired Mac confirmation

Heavy work from iPhone, iPad, or visionOS SHALL run on the Mac worker only after an
expiring pairing nonce is confirmed by the Mac user. Unconfirmed pairing SHALL NOT
change the client profile to `personal-full`.

#### Scenario: unconfirmed pairing
- **WHEN** an iOS job supplies a pairing id that has not been confirmed
- **THEN** `DelegationDenied` is raised and yt-dlp is not executed

#### Scenario: confirmed pairing lets mac execute without widening
- **WHEN** an iOS job supplies a confirmed pairing id and session key
- **THEN** the recorded policy profile stays `personal-restricted`, the Mac worker
  runs yt-dlp, and the job completes

### Requirement: Mac LAN relay

The Mac app SHALL listen on a private-LAN or loopback HTTP relay and rewrite
requests onto the loopback worker. The relay SHALL reject public internet peers
and `nativeCommand`. Complete clients SHALL paste an advertised private URL, not
the phone's own `127.0.0.1`.

#### Scenario: mac lan relay rewrites to loopback

- **WHEN** a complete-client POST reaches the Mac LAN relay
- **THEN** the host is rewritten to `127.0.0.1`, public peers are refused, and
  `nativeCommand` is rejected

#### Scenario: complete-client history uses mac relay

- **WHEN** iPhone, iPad, or visionOS refreshes history or pauses the queue
- **THEN** those requests target the saved private Mac URL, not the phone's
  loopback

#### Scenario: complete-client plan uses mac relay

- **WHEN** iPhone, iPad, or visionOS asks the Mac to explain a plan
- **THEN** the request targets the saved private Mac URL `/v1/plan`, not the
  phone's loopback

#### Scenario: complete-client doctor uses mac relay

- **WHEN** iPhone, iPad, or visionOS asks for worker doctor
- **THEN** the request targets the saved private Mac URL `/v1/doctor`, not the
  phone's loopback

#### Scenario: complete-client control intents use mac relay

- **WHEN** iPhone, iPad, or visionOS Siri/Shortcuts pause, resume, history, status,
  cancel, or pause/resume a job
- **THEN** those App Intents call `WebMediaDLCompleteClientControl` against the saved Mac URL
  and speak the relay response
