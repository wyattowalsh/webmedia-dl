# Delta: cross-device-workers

## ADDED Requirements

### Requirement: Explicit pairing

Pairing SHALL use an expiring nonce. Transport SHALL NOT decide capability policy.
A restricted client SHALL NOT delegate disallowed capabilities to a full worker.
Companion/Continuity transport SHALL NOT decide capability policy.

#### Scenario: restricted cannot delegate yt-dlp

- **WHEN** `personal-restricted` asks `personal-full` to run `acquire.ytdlp`
- **THEN** `DelegationDenied` is raised
