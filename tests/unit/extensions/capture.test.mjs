import { collectMediaEvidence } from "../../../extensions/shared/capture.js";
import assert from "node:assert/strict";
import { describe, it } from "node:test";

describe("collectMediaEvidence", () => {
  it("collects media URLs and never returns a native command", () => {
    const doc = {
      location: { href: "https://example.com/page" },
      querySelectorAll: () => [
        { tagName: "VIDEO", getAttribute: () => "https://cdn.example.com/a.mp4" },
        { tagName: "IMG", getAttribute: () => "javascript:alert(1)" },
      ],
      querySelector: () => ({ getAttribute: () => "https://cdn.example.com/og.png" }),
    };
    const result = collectMediaEvidence(doc);
    assert.equal(result.nativeCommand, null);
    assert.equal(result.pageUrl, "https://example.com/page");
    assert.deepEqual(
      result.evidence.map((item) => item.url),
      ["https://cdn.example.com/a.mp4", "https://cdn.example.com/og.png"],
    );
  });
});
