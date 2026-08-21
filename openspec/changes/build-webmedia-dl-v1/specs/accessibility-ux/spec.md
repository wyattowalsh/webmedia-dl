# Delta: accessibility-ux

## ADDED Requirements

### Requirement: Structured expert output, one-tap ordinary path

Ordinary submit SHALL be a single command or extension button. Expert inspection
SHALL be JSON events. Extension UI SHALL include `lang`, a labeled token field,
a keyboard-focusable button, and `aria-live` status.

#### Scenario: capture popup markup

- **WHEN** `extensions/chromium/popup.html` is inspected
- **THEN** it has `html lang`, a `label for="token"`, and `role="status"`
