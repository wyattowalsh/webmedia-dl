# Delta: accessibility-ux

## ADDED Requirements

### Requirement: Structured expert output, one-tap ordinary path

Ordinary submit SHALL be a single command or extension button. Expert inspection
SHALL be JSON events. Extension UI SHALL include `lang`, a labeled token field,
a keyboard-focusable button, and `aria-live` status.

#### Scenario: capture popup markup

- **WHEN** `extensions/chromium/popup.html` is inspected
- **THEN** it has `html lang`, a `label for="token"`, and `role="status"`

#### Scenario: one-tap extension submit

- **WHEN** the capture popup send button is clicked
- **THEN** the extension POSTs page URLs to the loopback worker in one tap

#### Scenario: expert output is JSON events

- **WHEN** `webmedia-dl submit` completes a local file job
- **THEN** stdout JSON includes a `job` object and a non-empty `events` list
