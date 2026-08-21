import { collectFromActiveTab, collectMediaEvidence } from "../../../extensions/shared/capture.js";
import assert from "node:assert/strict";
import { describe, it } from "node:test";

describe("collectMediaEvidence", () => {
  it("collects media URLs and never returns a native command", () => {
    const doc = {
      location: { href: "https://example.com/page" },
      querySelectorAll: (selector) => {
        if (selector.includes("ld+json")) {
          return [
            {
              textContent: JSON.stringify({
                "@graph": [{ contentUrl: "https://cdn.example.com/ld.mp4" }],
              }),
            },
          ];
        }
        if (selector === "meta") {
          return [
            {
              getAttribute: (name) =>
                name === "property" ? "og:image" : name === "content" ? "https://cdn.example.com/og.png" : null,
            },
          ];
        }
        return [
          { tagName: "VIDEO", getAttribute: () => "https://cdn.example.com/a.mp4" },
          { tagName: "IMG", getAttribute: () => "javascript:alert(1)" },
        ];
      },
    };
    const result = collectMediaEvidence(doc);
    assert.equal(result.nativeCommand, null);
    assert.equal(result.pageUrl, "https://example.com/page");
    const urls = result.evidence.map((item) => item.url);
    assert.ok(urls.includes("https://cdn.example.com/a.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/og.png"));
    assert.ok(urls.includes("https://cdn.example.com/ld.mp4"));
    assert.ok(!urls.some((item) => item.startsWith("javascript:")));
  });

  it("collectFromActiveTab falls back without a tabs API", async () => {
    const previous = globalThis.document;
    globalThis.document = {
      location: { href: "https://example.com/popup" },
      querySelectorAll: () => [],
    };
    try {
      const result = await collectFromActiveTab();
      assert.equal(result.nativeCommand, null);
      assert.equal(result.pageUrl, "https://example.com/popup");
    } finally {
      globalThis.document = previous;
    }
  });
});
