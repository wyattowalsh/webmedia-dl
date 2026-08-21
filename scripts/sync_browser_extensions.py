#!/usr/bin/env python3
"""Copy the shared capture module into each browser extension tree."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = (ROOT / "extensions/shared/capture.js").read_text(encoding="utf-8")

POPUP_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>WebMedia DL capture</title>
    <style>
      body {
        font-family: system-ui, sans-serif;
        margin: 12px;
        min-width: 240px;
      }
      button:focus {
        outline: 2px solid #005fcc;
      }
    </style>
  </head>
  <body>
    <h1>WebMedia DL</h1>
    <p>Send this tab's URL to the local worker.</p>
    <label for="token">Worker token</label>
    <input id="token" type="password" autocomplete="off" aria-required="true" />
    <button id="send" type="button">Send to worker</button>
    <p id="status" role="status" aria-live="polite"></p>
    <script type="module" src="popup.js"></script>
  </body>
</html>
"""

POPUP_JS = """import {{ collectMediaEvidence, submitToWorker, activeTabLocator }} from "./capture.js";

const SURFACE = "{surface}";
const button = document.getElementById("send");
const status = document.getElementById("status");
const tokenInput = document.getElementById("token");

button?.addEventListener("click", async () => {{
  try {{
    const evidence = collectMediaEvidence(document);
    status.textContent = `Captured ${{evidence.evidence.length}} local preview URL(s).`;
    const locator = (await activeTabLocator()) || evidence.pageUrl;
    if (!locator) {{
      status.textContent = "No page URL is available.";
      return;
    }}
    await submitToWorker("http://127.0.0.1:8765", tokenInput.value, locator, SURFACE, evidence.evidence);
    status.textContent = "Submitted to the local worker.";
  }} catch (error) {{
    status.textContent = error instanceof Error ? error.message : "Capture failed.";
  }}
}});
"""

BROWSERS = {
    "chromium": ("WebMedia DL Capture", "chromium", None),
    "chrome": ("WebMedia DL Capture for Chrome", "chrome", None),
    "brave": ("WebMedia DL Capture for Brave", "brave", None),
    "edge": ("WebMedia DL Capture for Edge", "edge", None),
    "firefox": (
        "WebMedia DL Capture",
        "firefox",
        {
            "gecko": {
                "id": "webmedia-dl@local",
                "strict_min_version": "121.0",
            }
        },
    ),
    "safari": ("WebMedia DL Capture", "safari", None),
}


def manifest(name: str, gecko: dict | None) -> dict:
    payload = {
        "manifest_version": 3,
        "name": name,
        "version": "0.1.0",
        "description": (
            "Capture page media evidence for the local WebMedia DL worker. "
            "Not a native command runner."
        ),
        "permissions": ["activeTab", "storage"],
        "host_permissions": ["http://127.0.0.1:8765/*"],
        "action": {
            "default_title": "Send to WebMedia DL",
            "default_popup": "popup.html",
        },
    }
    if gecko:
        payload["browser_specific_settings"] = gecko
    return payload


def main() -> None:
    import json

    for folder, (name, surface, gecko) in BROWSERS.items():
        dest = ROOT / "extensions" / folder
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "capture.js").write_text(SHARED, encoding="utf-8")
        (dest / "popup.html").write_text(POPUP_HTML, encoding="utf-8")
        (dest / "popup.js").write_text(POPUP_JS.format(surface=surface), encoding="utf-8")
        (dest / "manifest.json").write_text(
            json.dumps(manifest(name, gecko), indent=2) + "\n", encoding="utf-8"
        )
    safari = ROOT / "extensions/safari"
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>WebMedia DL</string>
  <key>CFBundleIdentifier</key>
  <string>local.webmedia-dl.safari</string>
  <key>NSExtension</key>
  <dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.Safari.web-extension</string>
    <key>NSExtensionPrincipalClass</key>
    <string>SafariWebExtensionHandler</string>
  </dict>
</dict>
</plist>
"""
    (safari / "Info.plist").write_text(plist, encoding="utf-8")
    readme = safari / "README.md"
    if not readme.is_file():
        readme.write_text(
            "# Safari Web Extension\n\nLoopback capture only. Xcode wrapping is BLOCKED on Linux CI.\n",
            encoding="utf-8",
        )
    print("synced", ", ".join(BROWSERS))


if __name__ == "__main__":
    main()
