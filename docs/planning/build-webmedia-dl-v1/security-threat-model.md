        ---
        title: "Security threat model"
        status: proposed
        type: planning
        change: build-webmedia-dl-v1
        last_reviewed: 2026-08-18
        ---
        # Security threat model

        Assets: user media, cookies, local token, pairing nonce.
Threats: SSRF via file: URLs, argv injection, DRM bypass, token theft, profile escalation.
Controls: loopback + bearer token, capability intersection, DRM refuse-closed, cookie absolute-path.
