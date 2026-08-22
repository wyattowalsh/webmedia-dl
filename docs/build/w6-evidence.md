# W6 evidence

- status: `PASS`
- scope: Browser capture extensions.
- reason: Browser capture extensions ship for Chromium, Chrome, Brave, Edge, Firefox, and Safari. Linux CI runs `node --test tests/unit/extensions/*.mjs` and pytest invokes that collector suite.
