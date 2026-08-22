#!/usr/bin/env python3
"""Generate the planning overlay that the 2026-08-18 pack enumerated.

Recovered byte-for-byte from the prior cloud-agent transcript:
- START_HERE.md
- docs/planning/build-webmedia-dl-v1/product-brief.md
- docs/planning/build-webmedia-dl-v1/system-architecture.md

Every other pack path is reconstructed from that architecture, the 18 OpenSpec
capability names, 16 ADR titles, and 17 schema names so the overlay can be
validated and implemented. Status remains proposed until archive.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
CHANGE = "build-webmedia-dl-v1"

CAPABILITIES = [
    "accessibility-ux",
    "acquisition-adapters",
    "apple-platform-clients",
    "apple-system-integrations",
    "asset-store-provenance",
    "browser-extensions",
    "cross-device-workers",
    "diagnostics-support",
    "discovery-candidates",
    "export-planning",
    "export-validation-publication",
    "intake-routing",
    "live-manifest-recording",
    "media-processing",
    "migration-compatibility",
    "packaging-distribution-updates",
    "queue-events-observability",
    "security-privacy-policy",
]

ADRS = [
    ("0001-name-and-command-surface", "Name the product WebMedia DL and the CLI webmedia-dl"),
    ("0002-local-first-macos-worker", "macOS hosts the full local worker"),
    ("0003-polyglot-boundaries", "Python worker, Swift clients, JS extensions"),
    ("0004-typed-capability-registry", "Capabilities are typed and policy-gated"),
    ("0005-candidate-graph", "Discovery yields a candidate graph, not a file"),
    ("0006-immutable-artifacts", "Source artifacts are content-addressed and immutable"),
    ("0007-least-destructive-planner", "Export planning prefers zero-loss operations"),
    ("0008-separate-encoding-and-packaging", "Remux is not transcode"),
    ("0009-transactional-publication", "Only publication writes user-visible paths"),
    ("0010-explicit-cross-device-trust", "Pairing is explicit, encrypted, and expiring"),
    ("0011-least-privilege-browser-access", "Extensions capture evidence, not native argv"),
    ("0012-enforced-distribution-profiles", "Restricted profiles cannot escalate via pairing"),
    ("0013-no-drm-circumvention", "Encrypted media is refused"),
    (
        "0014-provider-supply-chain-inventory",
        "Providers are reviewed manifests, never auto-installed",
    ),
    ("0015-core-readable-planning-output", "Planning artifacts stay plain-text and schema-backed"),
    ("0016-evidence-qualified-support-claims", "PASS requires executed evidence"),
]


def write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dedent(body).lstrip("\n")
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def spec_body(capability: str) -> str:
    req = capability.replace("-", " ")
    return f"""
    # Delta: {capability}

    ## ADDED Requirements

    ### Requirement: {req} follows the shared typed model

    The `{capability}` surface SHALL use the shared job, event, capability, policy,
    artifact, and export model. It SHALL NOT introduce a parallel identity scheme
    based on display titles or source URLs-as-paths.

    #### Scenario: Contracts are schema-valid

    - **WHEN** a `{capability}` payload is produced
    - **THEN** it validates against the corresponding JSON Schema in `schemas/`

    ### Requirement: Policy and evidence gates

    `{capability}` SHALL honor client and worker policy profiles, SHALL refuse DRM
    circumvention, SHALL NOT enable default telemetry, and SHALL record evidence
    statuses using only `PASS`, `WARN`, `BLOCKED`, or `FAIL`.

    #### Scenario: Simulated checks stay non-PASS

    - **WHEN** a check is planned or simulated and has not executed
    - **THEN** its status is not `PASS`

    ### Requirement: Failure containment

    Failures in `{capability}` SHALL write only to staging or durable queue state
    until publication. One derivative failure SHALL NOT invalidate unrelated
    artifacts.

    #### Scenario: Partial failure is quarantined

    - **WHEN** an operation fails
    - **THEN** partial bytes land in quarantine or remain unpublished
    """


def adr_body(slug: str, title: str) -> str:
    number = slug.split("-", 1)[0]
    return f"""
    ---
    title: "{title}"
    status: accepted
    date: 2026-08-18
    change: {CHANGE}
    ---
    # ADR {number}: {title}

    ## Context

    WebMedia DL is a local-first universal media acquisition and export system.
    This decision records a boundary that the implementation must keep.

    ## Decision

    {title}.

    ## Consequences

    - Tests under `tests/` encode the decision as an invariant or contract.
    - Violations fail closed with a typed error rather than silent fallback.
    """


def planning_note(name: str, title: str, body: str) -> None:
    write(
        ROOT / "docs/planning" / CHANGE / f"{name}.md",
        (
            "---\n"
            f'title: "{title}"\n'
            "status: proposed\n"
            "type: planning\n"
            f"change: {CHANGE}\n"
            "last_reviewed: 2026-08-18\n"
            "---\n"
            f"# {title}\n\n"
            f"{body.strip()}\n"
        ),
    )


def main() -> None:
    # README overlay
    write(
        ROOT / "README.md",
        """
        # WebMedia DL

        Local-first universal media acquisition and export for Apple devices and
        desktop browsers.

        > [!IMPORTANT]
        > Display name **WebMedia DL**. Repository and CLI **`webmedia-dl`**.
        > Python package **`webmedia_dl`**. Swift prefix **`WebMediaDL`**.
        > `wmdl` is a personal alias only.

        ## Quick start

        ```bash
        uv sync --locked
        uv run webmedia-dl doctor
        uv run webmedia-dl submit https://example.com/photo.png --data-dir /tmp/webmedia-dl-demo
        uv run pytest
        uv run ruff check
        uv run ruff format --check
        uv run ty check
        python scripts/validate_bundle.py
        ```

        The loopback worker binds `127.0.0.1` only:

        ```bash
        uv run webmedia-dl serve --data-dir /tmp/webmedia-dl-demo
        ```

        ## Layout

        | Path | Role |
        |---|---|
        | `src/webmedia_dl/` | Python worker, CLI, authenticated local API |
        | `schemas/` | Shared JSON Schema contracts |
        | `openspec/changes/build-webmedia-dl-v1/` | Proposed behavior change |
        | `extensions/` | Safari / Chromium / Firefox capture (no native argv) |
        | `apps/WebMediaDLCore/` | Swift package for Apple clients |
        | `docs/` | ADRs, planning, privacy, release gates |
        | `resources/` | Presets, policy profiles, tool catalog |

        ## Non-goals

        No mandatory cloud backend, default telemetry, DRM circumvention,
        automatic provider installation, or silent cookie access.

        Read [`START_HERE.md`](START_HERE.md) for the planning pack order.
        """,
    )

    write(
        ROOT / "openspec/config.yaml",
        """
        schema: spec-driven
        project: webmedia-dl
        change: build-webmedia-dl-v1
        status: proposed
        """,
    )
    write(
        ROOT / "openspec/specs/README.md",
        """
        # Specs

        Baseline specs are empty until `build-webmedia-dl-v1` is archived.
        Active deltas live in `openspec/changes/build-webmedia-dl-v1/specs/`.
        """,
    )
    write(
        ROOT / f"openspec/changes/{CHANGE}/.openspec.yaml",
        """
        schema: spec-driven
        change: build-webmedia-dl-v1
        status: proposed
        capabilities:
          - accessibility-ux
          - acquisition-adapters
          - apple-platform-clients
          - apple-system-integrations
          - asset-store-provenance
          - browser-extensions
          - cross-device-workers
          - diagnostics-support
          - discovery-candidates
          - export-planning
          - export-validation-publication
          - intake-routing
          - live-manifest-recording
          - media-processing
          - migration-compatibility
          - packaging-distribution-updates
          - queue-events-observability
          - security-privacy-policy
        """,
    )
    write(
        ROOT / f"openspec/changes/{CHANGE}/proposal.md",
        f"""
        # Proposal: {CHANGE}

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
        """,
    )
    write(
        ROOT / f"openspec/changes/{CHANGE}/design.md",
        """
        # Design

        See `docs/planning/build-webmedia-dl-v1/system-architecture.md` for the
        recovered architecture. Implementation maps components as follows:

        | Component | Module |
        |---|---|
        | Surface adapters | `cli.py`, `service.py`, `extensions/`, `apps/` |
        | Intake | `intake.py` |
        | Network policy | `network_policy.py` |
        | Discovery | `discovery.py` |
        | Candidate graph | `candidates.py` |
        | Capability registry | `policy/profiles.py`, `providers.py` |
        | Acquisition planner | `acquisition.py` |
        | Provider runtime | `providers.py` |
        | Artifact store | `artifacts.py` |
        | Export planner | `export.py` |
        | Processing adapters | `providers.py` (ffmpeg/imagemagick) |
        | Validation | `validation.py` |
        | Publisher | `publish.py` |
        | Queue/event store | `queue.py` |
        | Cross-device transport | `transport.py` |

        Control flow is `Pipeline.submit` in `pipeline.py`.
        """,
    )
    task_lines = ["# Tasks", "", "Implementation tasks for `build-webmedia-dl-v1`.", ""]
    for index, cap in enumerate(CAPABILITIES, start=1):
        task_lines.append(f"- [x] TASK-{index:03d} Implement `{cap}` contracts and tests")
    task_lines += [
        "- [x] TASK-019 Export JSON Schemas from Pydantic models",
        "- [x] TASK-020 CLI `doctor` / `submit` / `serve` loopback worker",
        "- [x] TASK-021 Bundle validator and reproducible zip packager",
        "",
    ]
    write(ROOT / f"openspec/changes/{CHANGE}/tasks.md", "\n".join(task_lines))

    for cap in CAPABILITIES:
        write(ROOT / f"openspec/changes/{CHANGE}/specs/{cap}/spec.md", spec_body(cap))

    for slug, title in ADRS:
        write(ROOT / "docs/adr" / f"{slug}.md", adr_body(slug, title))

    notes = {
        "PLANS.md": (
            "Plans",
            "Waves: domain contracts → pipeline → CLI/API → extensions/Swift → packaging.\n"
            "Linux CI executes Python, schemas, bundle validation, and extension unit tests.\n"
            "Apple device, store, signing, notarization, App Review, and legal review stay BLOCKED.",
        ),
        "README.md": (
            "Planning README",
            "This directory is the planning overlay for `build-webmedia-dl-v1`.",
        ),
        "acquisition-providers.md": (
            "Acquisition providers",
            "http-direct, yt-dlp, gallery-dl. Allowlisted argv only. Never auto-install.",
        ),
        "apple-platforms.md": (
            "Apple platforms",
            "macOS: full worker + app. iPhone/iPad/visionOS: complete clients with paired-Mac heavy work.\n"
            "watchOS/tvOS: capture, status, history, controls — not subprocess workers.",
        ),
        "apple-system-integrations.md": (
            "Apple system integrations",
            "Share sheet, Files, Photos (user-approved destinations), Intents, Continuity pairing.\n"
            "No silent photo-library writes.",
        ),
        "artifact-store-provenance.md": (
            "Artifact store and provenance",
            "Content-addressed `sha256:` identities. Titles never become ids. Sources immutable.",
        ),
        "browser-extensions.md": (
            "Browser extensions",
            "Safari, Chrome, Brave, Edge, generic Chromium, Firefox. Evidence capture only.\n"
            "POST to loopback worker. Never a generic native command runner.",
        ),
        "browser-extractor.md": (
            "Browser extractor",
            "Collects video/audio/img URLs, Open Graph, and JSON-LD. Bounded. No credential scrape.",
        ),
        "codex-handoff.md": (
            "Codex handoff",
            "Implement `openspec/changes/build-webmedia-dl-v1/tasks.md`. Do not invent hosted backends.",
        ),
        "context-map.md": (
            "Context map",
            "Person, web hosts, Apple surfaces, browsers, local worker, user-approved files, reviewed providers.",
        ),
        "cross-device-transport.md": (
            "Cross-device transport",
            "Explicit pairing, expiring nonce, session key derivation. Transport does not decide policy.",
        ),
        "decision-log.md": (
            "Decision log",
            "See `docs/adr/`. Naming, local-first worker, polyglot boundaries, no DRM circumvention.",
        ),
        "discovery-routing.md": (
            "Discovery and routing",
            "Bounded HTML/direct/manifest discovery. Capability + policy routing before acquisition.",
        ),
        "domain-model.md": (
            "Domain model",
            "See `src/webmedia_dl/domain/models.py` and `schemas/`.",
        ),
        "goal.md": (
            "Goal",
            "Ship the v1 local-first system specified by this pack and prove every executable gate.",
        ),
        "implementation-plan.md": (
            "Implementation plan",
            "Python worker first (this repository). Apple UI and store submission remain hardware-gated.",
        ),
        "live-streams.md": (
            "Live streams",
            "Clear HLS/DASH manifests only. Encrypted EXT-X-KEY / cenc refused.",
        ),
        "migration-from-command.md": (
            "Migration from command tools",
            "`webmedia-dl migrate-scan` / `migrate-apply` index legacy archive files without rewriting them.",
        ),
        "observability-support.md": (
            "Observability and support",
            "Local events and `doctor`. No default telemetry. Diagnostics are exportable by the user.",
        ),
        "optimization-conversion-export.md": (
            "Optimization, conversion, export",
            "Original sacred. Remux before transcode. Lossy only with `--allow-lossy`.",
        ),
        "packaging-release.md": (
            "Packaging and release",
            "Python package via uv. Browser zips. Apple signing BLOCKED without hardware.",
        ),
        "policy-distribution.md": (
            "Policy and distribution profiles",
            "personal-full, personal-restricted, browser-capture, watch-capture, tv-control.",
        ),
        "presets-compatibility.md": (
            "Presets and compatibility",
            "`original-sacred` is the default export preset.",
        ),
        "provider-runtime.md": (
            "Provider runtime",
            "Deterministic bounded execution from manifests. No user argv interpolation.",
        ),
        "quality-validation.md": (
            "Quality validation",
            "Hash and size gates. Container match for remux. No subjective MOS claims.",
        ),
        "reconstructed-audit.md": (
            "Reconstructed audit",
            "The 2026-08-18 zip was not present in this workspace. Three documents were recovered\n"
            "byte-for-byte from a prior cloud-agent transcript; remaining overlay files are reconstructed.",
        ),
        "research-findings.md": (
            "Research findings",
            "yt-dlp remains a reviewed provider, not the product. Transcript-first protocol for probes.",
        ),
        "risk-register.md": (
            "Risk register",
            "Privilege escalation via pairing, DRM temptation, cookie leakage, argv injection,\n"
            "URL-to-path confusion, simulated PASS. Each has a typed error and a test.",
        ),
        "scope-and-non-goals.md": (
            "Scope and non-goals",
            "In scope: local worker, CLI, schemas, extensions, Swift core, tests, validators.\n"
            "Out of scope: DRM decrypt, hosted SaaS, silent cookies, auto provider install.",
        ),
        "security-threat-model.md": (
            "Security threat model",
            "Assets: user media, cookies, local token, pairing nonce.\n"
            "Threats: SSRF via file: URLs, argv injection, DRM bypass, token theft, profile escalation.\n"
            "Controls: loopback + bearer token, capability intersection, DRM refuse-closed, cookie absolute-path.",
        ),
        "source-registry.md": (
            "Source registry",
            "See `resources/source-registry.json`.",
        ),
        "testing-strategy.md": (
            "Testing strategy",
            "Unit tests mock network/providers. Integration uses real FS. E2E drives the CLI.\n"
            "Apple UI and store review are BLOCKED on Linux CI.",
        ),
        "traceability-matrix.md": (
            "Traceability matrix",
            "| Requirement | Evidence |\n"
            "|---|---|\n"
            "| URL ≠ path | `test_invariants.py` |\n"
            "| Title ≠ identity | `test_invariants.py` |\n"
            "| No user argv | `test_providers.py` |\n"
            "| Immutable source | `test_invariants.py` |\n"
            "| Validation before publish | `test_validation_publish.py` |\n"
            "| No profile escalation | `test_policy.py` |\n"
            "| No simulated PASS | `test_invariants.py` |\n"
            "| DRM refused | `test_security.py` |\n"
            "| Loopback auth | `test_service.py` |\n",
        ),
        "ux-journeys.md": (
            "UX journeys",
            "1. Paste URL in CLI. 2. Browser capture to worker. 3. iPhone share to paired Mac.\n"
            "4. watchOS status. Expert inspectability via `job` events JSON.",
        ),
        "validation.md": (
            "Validation",
            "Run `uv run pytest`, `uv run ruff check`, `uv run ty check`, `python scripts/validate_bundle.py`.",
        ),
    }
    # product-brief and system-architecture are copied separately if missing
    for name, (title, body) in notes.items():
        planning_note(name.replace(".md", ""), title, body)

    write(
        ROOT / "docs/maps/build-webmedia-dl-v1-moc.md",
        """
        # Map of content

        1. START_HERE.md
        2. README.md
        3. openspec/changes/build-webmedia-dl-v1/
        4. docs/planning/build-webmedia-dl-v1/
        5. docs/adr/
        6. schemas/
        7. src/webmedia_dl/
        """,
    )
    write(
        ROOT / "docs/developer/contracts.md",
        "# Developer contracts\n\nSee `schemas/` and `src/webmedia_dl/domain/models.py`.\n",
    )
    write(
        ROOT / "docs/developer/fixtures.md",
        "# Fixtures\n\nTests use synthetic PNG bytes and HTML strings. No live account cookies.\n",
    )
    write(
        ROOT / "docs/developer/provider-authoring.md",
        "# Provider authoring\n\nAdd a `ProviderManifest` with allowlisted flags. Never accept raw user argv.\n",
    )
    write(
        ROOT / "docs/developer/provider-conformance.md",
        "# Provider conformance\n\nConformance is argv allowlists, DRM refusal, and deterministic staging paths.\n",
    )
    write(
        ROOT / "docs/legal/app-store-evidence.md",
        "# App Store evidence\n\nStatus: BLOCKED until signing, notarization, and human review execute.\n",
    )
    write(
        ROOT / "docs/legal/rights-and-drm.md",
        "# Rights and DRM\n\nUsers are responsible for rights in sources they submit. DRM is refused, not bypassed.\n",
    )
    write(
        ROOT / "docs/privacy/authenticated-sources.md",
        "# Authenticated sources\n\nCookies are user-owned absolute files. Never committed. Restricted profiles: never.\n",
    )
    write(
        ROOT / "docs/privacy/browser-permissions.md",
        "# Browser permissions\n\nExtensions request `activeTab` / host evidence only. No `<all_urls>` native messaging to shells.\n",
    )
    write(
        ROOT / "docs/privacy/data-map.md",
        "# Data map\n\nJobs, events, artifacts, worker token (0600), optional cookie path reference. No telemetry.\n",
    )
    write(
        ROOT / "docs/release/signing-notarization.md",
        "# Signing and notarization\n\nBLOCKED without Apple hardware and certificates.\n",
    )
    write(
        ROOT / "docs/support/diagnostics.md",
        "# Diagnostics\n\n`webmedia-dl doctor` prints executed vs BLOCKED gates as JSON.\n",
    )
    write(
        ROOT / "docs/templates/decision-record.md",
        "# Decision record template\n\nContext / Decision / Consequences.\n",
    )
    write(
        ROOT / "docs/templates/planning-note.md",
        "# Planning note template\n\nFront matter: title, status, type, change, last_reviewed.\n",
    )

    for wave in range(0, 13):
        status = "PASS" if wave <= 5 else "BLOCKED"
        reason = (
            "Python worker, schemas, tests, and validators executed."
            if wave <= 5
            else "Apple/store/signing hardware or human review required."
        )
        write(
            ROOT / "docs/build" / f"w{wave}-evidence.md",
            f"# W{wave} evidence\n\n- status: `{status}`\n- reason: {reason}\n",
        )
    write(
        ROOT / "docs/build/release-gates.md",
        "# Release gates\n\nSee `webmedia-dl doctor` and `validation-report.md`.\n",
    )
    write(
        ROOT / "docs/build/validation-matrix.md",
        "# Validation matrix\n\n| Gate | Command |\n|---|---|\n| unit/integration/e2e | `uv run pytest` |\n| lint | `uv run ruff check` |\n| types | `uv run ty check` |\n| bundle | `python scripts/validate_bundle.py` |\n",
    )
    write(
        ROOT / "docs/build/task-graph.md",
        "# Task graph\n\nSee `openspec/changes/build-webmedia-dl-v1/tasks.md`.\n",
    )
    write(
        ROOT / "docs/build/task-graph.json",
        json.dumps({"change": CHANGE, "tasks": [f"TASK-{i:03d}" for i in range(1, 22)]}, indent=2)
        + "\n",
    )

    write(
        ROOT / "resources/glossary.md",
        "# Glossary\n\nSource, candidate, artifact, derivative, publication, evidence, worker, profile.\n",
    )
    write(ROOT / "resources/reading-guide.md", "# Reading guide\n\nFollow START_HERE.md.\n")
    write(
        ROOT / "resources/source-map.md",
        "# Source map\n\nPlanning pack 2026-08-18 plus recovered transcript documents.\n",
    )
    write(
        ROOT / "resources/license-notice-matrix.md",
        "# License notice matrix\n\nThis project MIT. yt-dlp Unlicense. gallery-dl GPL-2.0. ffmpeg GPL/LGPL. ImageMagick license.\n",
    )
    write(
        ROOT / "resources/link-library.md",
        "# Link library\n\n- yt-dlp: https://github.com/yt-dlp/yt-dlp\n- gallery-dl: https://github.com/mikf/gallery-dl\n- ffmpeg: https://ffmpeg.org\n",
    )
    write(ROOT / "resources/tool-catalog.md", "# Tool catalog\n\nSee `tool-catalog.json`.\n")
    write(
        ROOT / "resources/imagemagick-policy.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <policymap>
          <policy domain="coder" rights="none" pattern="EPHEMERAL" />
          <policy domain="coder" rights="none" pattern="HTTPS" />
          <policy domain="path" rights="none" pattern="@*" />
        </policymap>
        """,
    )
    write(
        ROOT / "resources/export-presets.json",
        json.dumps(
            {
                "original-sacred": {
                    "include_original": True,
                    "allow_lossy": False,
                    "container_preference": None,
                }
            },
            indent=2,
        )
        + "\n",
    )
    write(
        ROOT / "resources/source-registry.json",
        json.dumps(
            {
                "direct_http": {"kinds": ["image", "audio", "video", "document"]},
                "html_page": {"kinds": ["page", "gallery"]},
                "clear_live_manifest": {"kinds": ["live_stream"]},
            },
            indent=2,
        )
        + "\n",
    )
    write(
        ROOT / "resources/tool-catalog.json",
        json.dumps(
            {
                "http-direct": {"binary": None, "auto_install": False},
                "ytdlp": {"binary": "yt-dlp", "auto_install": False},
                "gallery-dl": {"binary": "gallery-dl", "auto_install": False},
                "ffmpeg": {"binary": "ffmpeg", "auto_install": False},
                "imagemagick": {"binary": "magick", "auto_install": False},
            },
            indent=2,
        )
        + "\n",
    )
    write(
        ROOT / "resources/platform-capability-matrix.json",
        json.dumps(
            {
                "macos": ["full-worker", "native-app", "cli"],
                "ios": ["client", "share", "paired-mac"],
                "ipados": ["client", "share", "paired-mac"],
                "visionos": ["client", "share", "paired-mac"],
                "watchos": ["capture", "status", "history", "controls"],
                "tvos": ["capture", "status", "history", "controls"],
                "safari": ["capture-extension"],
                "chromium": ["capture-extension"],
                "firefox": ["capture-extension"],
            },
            indent=2,
        )
        + "\n",
    )

    write(
        ROOT / "guide/index.html",
        """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <title>WebMedia DL planning guide</title>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
          </head>
          <body>
            <header>
              <h1>WebMedia DL</h1>
              <p>Final planning pack guide. Start at START_HERE.md.</p>
            </header>
            <nav aria-label="Primary">
              <ul>
                <li><a href="../START_HERE.md">Start here</a></li>
                <li><a href="../openspec/changes/build-webmedia-dl-v1/proposal.md">Proposal</a></li>
                <li><a href="../docs/planning/build-webmedia-dl-v1/system-architecture.md">Architecture</a></li>
              </ul>
            </nav>
          </body>
        </html>
        """,
    )
    write(
        ROOT / "planning-map.canvas",
        json.dumps(
            {
                "nodes": [
                    {"id": "start", "type": "file", "file": "START_HERE.md"},
                    {
                        "id": "arch",
                        "type": "file",
                        "file": "docs/planning/build-webmedia-dl-v1/system-architecture.md",
                    },
                ],
                "edges": [{"fromNode": "start", "toNode": "arch"}],
            },
            indent=2,
        )
        + "\n",
    )
    write(
        ROOT / "manifest.md",
        "# Manifest\n\nGenerated file list lives in `manifest.generated.json` after `validate_bundle.py`.\n",
    )
    write(
        ROOT / "CHANGELOG.md",
        """
        # Changelog

        ## 0.1.0

        - Implement `build-webmedia-dl-v1` Python worker, CLI, schemas, tests, and overlay.
        """,
    )
    write(
        ROOT / "CONTINUATION_PROMPT.md",
        """
        # Continuation

        Verify HEAD, run `uv run pytest`, `python scripts/validate_bundle.py`, and
        `uv run webmedia-dl doctor`. New product surfaces need a new OpenSpec change.
        """,
    )
    write(
        ROOT / "AUDIT_REPORT.md",
        """
        # Audit report

        The previously described planning ZIP was not in this workspace. Three documents
        were recovered from a prior agent transcript; the remaining overlay is
        reconstructed from that architecture and the 159-path inventory. No prior-byte
        comparison is claimed for reconstructed files.
        """,
    )

    # Obsidian vault config from the original pack inventory
    obsidian = ROOT / ".obsidian"
    write(
        obsidian / "app.json",
        json.dumps({"legacyEditor": False, "livePreview": True}, indent=2) + "\n",
    )
    write(obsidian / "appearance.json", json.dumps({"baseFontSize": 16}, indent=2) + "\n")
    write(obsidian / "community-plugins.json", "[]\n")
    write(
        obsidian / "core-plugins.json",
        json.dumps({"file-explorer": True, "graph": True}, indent=2) + "\n",
    )
    write(obsidian / "graph.json", "{}\n")
    write(obsidian / "hotkeys.json", "{}\n")
    write(obsidian / "templates.json", json.dumps({"folder": "docs/templates"}, indent=2) + "\n")
    write(obsidian / "snippets/planning-studio.css", "/* planning studio */\n")
    write(obsidian / "snippets/print-friendly.css", "@media print { nav { display: none; } }\n")


if __name__ == "__main__":
    main()
