import {
  collectFromActiveTab,
  collectMediaEvidence,
  loadWorkerToken,
  saveWorkerToken,
  submitToWorker,
  WORKER_TOKEN_KEY,
} from "../../../extensions/shared/capture.js";
import assert from "node:assert/strict";
import { describe, it } from "node:test";

describe("collectMediaEvidence", () => {
  it("collects media URLs and never returns a native command", () => {
    const doc = {
      location: { href: "https://example.com/page" },
      querySelectorAll: (selector) => {
        if (selector.includes("iframe") || selector.includes("link[href]")) {
          return [];
        }
        if (selector.includes("ld+json")) {
          return [
            {
              textContent: JSON.stringify({
                "@graph": [
                  { contentUrl: "https://cdn.example.com/ld.mp4" },
                  { contentUrl: { "@id": "https://cdn.example.com/oid.mp4" } },
                ],
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
    assert.ok(urls.includes("https://cdn.example.com/oid.mp4"));
    assert.ok(!urls.some((item) => item.startsWith("javascript:")));
  });

  it("collects iframe and link preload media", () => {
    const doc = {
      location: { href: "https://example.com/page" },
      querySelectorAll: (selector) => {
        if (selector.includes("iframe")) {
          return [{ getAttribute: (name) => (name === "src" ? "https://cdn.example.com/live.m3u8" : null) }];
        }
        if (selector.includes("link[href]")) {
          return [
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/pre.mp4";
                if (name === "as") return "video";
                if (name === "rel") return "preload";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/still.png";
                if (name === "as") return "image";
                if (name === "rel") return "preload";
                return null;
              },
            },
          ];
        }
        return [];
      },
    };
    const result = collectMediaEvidence(doc);
    const urls = result.evidence.map((item) => item.url);
    assert.ok(urls.includes("https://cdn.example.com/live.m3u8"));
    assert.ok(urls.includes("https://cdn.example.com/pre.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/still.png"));
    assert.equal(result.nativeCommand, null);
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

  it("persists the worker token in extension storage", async () => {
    const store = {};
    const area = {
      get: (key) => Promise.resolve({ [key]: store[key] }),
      set: (items) => {
        Object.assign(store, items);
        return Promise.resolve();
      },
    };
    await saveWorkerToken("secret-token", area);
    assert.equal(store[WORKER_TOKEN_KEY], "secret-token");
    assert.equal(await loadWorkerToken(area), "secret-token");
  });

  it("submitToWorker requires a token", async () => {
    await assert.rejects(
      () => submitToWorker("http://127.0.0.1:8765", "  ", "https://example.com"),
      /Worker token is required/,
    );
  });

  it("submitToWorker posts browser evidence through fetch", async () => {
    const calls = [];
    const previous = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({ job_id: "job-1" }) };
    };
    try {
      const result = await submitToWorker(
        "http://127.0.0.1:8765",
        "worker-token",
        "https://example.com/watch",
        "chromium",
        [{ url: "https://cdn.example.com/a.mp4", kind: "video" }],
      );
      assert.equal(result.job_id, "job-1");
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, "http://127.0.0.1:8765/v1/jobs");
      assert.equal(calls[0].options.headers.Authorization, "Bearer worker-token");
      const body = JSON.parse(calls[0].options.body);
      assert.equal(body.intake_kind, "browser_evidence");
      assert.equal(body.locator, "https://example.com/watch");
      assert.equal(body.nativeCommand, undefined);
    } finally {
      globalThis.fetch = previous;
    }
  });

  it("popup send button posts one-tap capture to the loopback worker", async () => {
    const store = {};
    const tokenEl = { value: "worker-token" };
    const statusEl = { textContent: "" };
    const sendEl = {
      listeners: {},
      addEventListener(name, fn) {
        this.listeners[name] = fn;
      },
    };
    const previous = {
      document: globalThis.document,
      fetch: globalThis.fetch,
      chrome: globalThis.chrome,
    };
    globalThis.document = {
      getElementById(id) {
        if (id === "send") return sendEl;
        if (id === "status") return statusEl;
        if (id === "token") return tokenEl;
        return null;
      },
      location: { href: "https://example.com/watch" },
      querySelectorAll(selector) {
        if (String(selector).includes("video")) {
          return [
            {
              tagName: "VIDEO",
              getAttribute: () => "https://cdn.example.com/a.mp4",
            },
          ];
        }
        return [];
      },
    };
    const calls = [];
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({ job_id: "job-popup" }) };
    };
    globalThis.chrome = {
      storage: {
        local: {
          get: (key) => Promise.resolve({ [key]: store[key] }),
          set: (items) => {
            Object.assign(store, items);
            return Promise.resolve();
          },
        },
      },
    };
    try {
      await import("../../../extensions/chromium/popup.js");
      assert.equal(typeof sendEl.listeners.click, "function");
      await sendEl.listeners.click();
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, "http://127.0.0.1:8765/v1/jobs");
      assert.equal(calls[0].options.headers.Authorization, "Bearer worker-token");
      const body = JSON.parse(calls[0].options.body);
      assert.equal(body.intake_kind, "browser_evidence");
      assert.equal(body.locator, "https://example.com/watch");
      assert.equal(body.nativeCommand, undefined);
      assert.ok(body.evidence.some((item) => item.url === "https://cdn.example.com/a.mp4"));
      assert.equal(statusEl.textContent, "Submitted to the local worker.");
      assert.equal(store[WORKER_TOKEN_KEY], "worker-token");
    } finally {
      globalThis.document = previous.document;
      globalThis.fetch = previous.fetch;
      globalThis.chrome = previous.chrome;
    }
  });
});
