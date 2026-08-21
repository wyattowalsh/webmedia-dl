# Delta: asset-store-provenance

## ADDED Requirements

### Requirement: Content-addressed immutable sources

Source artifacts SHALL be identified as `sha256:<digest>`. After registration, source
bytes SHALL NOT be mutated. Display titles SHALL NOT be used as artifact ids.

#### Scenario: mutate source fails

- **WHEN** code attempts to overwrite a registered source
- **THEN** `ArtifactImmutabilityError` is raised
