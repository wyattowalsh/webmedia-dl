# Delta: cross-device-workers

## ADDED Requirements

### Requirement: Explicit pairing

Pairing SHALL use an expiring nonce. Transport SHALL NOT decide capability policy.
A restricted client SHALL NOT delegate disallowed capabilities to a full worker.
Companion/Continuity transport SHALL NOT decide capability policy.

#### Scenario: restricted cannot delegate yt-dlp

- **WHEN** `personal-restricted` asks `personal-full` to run `acquire.ytdlp`
- **THEN** `DelegationDenied` is raised

#### Scenario: pairing challenges expire

- **WHEN** a pairing challenge TTL elapses
- **THEN** `expired` is true and confirm/require fail closed

#### Scenario: consumed envelope nonces expire from the ledger

- **WHEN** a consumed pairing envelope nonce is older than the ledger retention window
- **THEN** the ledger forgets that row so `nonces.sqlite` cannot grow without bound; a later consume of the same nonce is recorded and a replay is denied
