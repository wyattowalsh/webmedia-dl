# Proposal: build-webmedia-dl-v1

## Why

`webmedia-dl` is a greenfield repository. Users need one local-first system
that can share, paste, drop, or capture a source, explain a least-destructive
plan, run it on the right device, validate the result, and keep originals
plus provenance intact — without becoming a GUI for unbounded yt-dlp argv.

## What changes

- Adopt the shared typed job/event/capability/policy/artifact/export model.
- Ship a Python local worker and `webmedia-dl` CLI on loopback.
- Define Apple client and browser-extension contracts that cannot escalate
  privilege or run native commands.
- Refuse DRM circumvention, silent cookies, default telemetry, and automatic
  provider installs.

## Non-goals (this change)

Hosted multi-tenant backends, App Store submission, notarization, and human
legal review remain `BLOCKED` evidence — they are release gates, not v1 code
on Linux CI.
