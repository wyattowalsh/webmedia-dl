---
title: "Browser extensions"
status: proposed
type: planning
change: build-webmedia-dl-v1
last_reviewed: 2026-08-18
---
# Browser extensions

Safari, Chrome, Brave, Edge, generic Chromium, Firefox. Evidence capture only.
POST to loopback worker. Never a generic native command runner. The Safari
native handler encodes JSON with `try`, refuses non-2xx worker responses, and
`cancelRequest`s instead of completing an empty or failed submit.
