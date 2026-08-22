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
      baseURI: "https://cdn.example.com/media/",
      querySelectorAll: (selector) => {
        if (selector.includes("iframe") || selector.includes("link[href]")) {
          return [];
        }
        if (selector.includes('type^="application/ld+json"')) {
          return [
            {
              textContent: JSON.stringify({
                "@graph": [
                  { contentUrl: "https://cdn.example.com/ld.mp4" },
                  { contentUrl: { "@id": "https://cdn.example.com/oid.mp4" } },
                  {
                    contentUrl: "https://cdn.example.com/charset.mp4",
                    "@type": "VideoObject",
                  },
                ],
              }),
            },
            {
              textContent:
                '<!--{"@type":"VideoObject","contentUrl":"https://cdn.example.com/commented.mp4"}-->',
            },
            {
              textContent:
                '<![CDATA[{"@type":"VideoObject","contentUrl":"https://cdn.example.com/cdata.mp4"}]]>',
            },
            {
              textContent:
                '{&quot;@type&quot;:&quot;VideoObject&quot;,&quot;contentUrl&quot;:&quot;https://cdn.example.com/escaped.mp4&quot;}',
            },
          ];
        }
        if (selector.includes("ld+json")) {
          return [];
        }
        if (selector === "meta") {
          return [
            {
              getAttribute: (name) =>
                name === "property" ? "og:image" : name === "content" ? "https://cdn.example.com/og.png" : null,
            },
            {
              getAttribute: (name) =>
                name === "property"
                  ? "og:image:secure_url"
                  : name === "content"
                    ? "https://cdn.example.com/secure.png"
                    : null,
            },
          ];
        }
        return [
          { tagName: "VIDEO", getAttribute: () => "https://cdn.example.com/a.mp4" },
          { tagName: "IMG", getAttribute: () => "javascript:alert(1)" },
          { tagName: "IMG", getAttribute: () => "data:image/png;base64,AAAA" },
          { tagName: "IMG", getAttribute: () => "file:/tmp/secret.png" },
        ];
      },
    };
    const result = collectMediaEvidence(doc);
    assert.equal(result.nativeCommand, null);
    assert.equal(result.pageUrl, "https://example.com/page");
    const urls = result.evidence.map((item) => item.url);
    assert.ok(urls.includes("https://cdn.example.com/a.mp4"));
    assert.ok(!urls.includes("https://cdn.example.com/media/a.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/og.png"));
    assert.ok(urls.includes("https://cdn.example.com/secure.png"));
    assert.equal(
      result.evidence.find((item) => item.url === "https://cdn.example.com/secure.png")?.kind,
      "image",
    );
    assert.ok(urls.includes("https://cdn.example.com/ld.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/oid.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/charset.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/commented.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/cdata.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/escaped.mp4"));
    assert.ok(!urls.some((item) => item.startsWith("javascript:")));
    assert.ok(!urls.some((item) => item.startsWith("data:")));
    assert.ok(!urls.some((item) => item.startsWith("file:")));
  });

  it("resolves relative locators against document.baseURI", () => {
    const doc = {
      location: { href: "https://watch.example.com/page" },
      ownerDocument: {
        baseURI: "https://cdn.example.com/media/",
        location: { href: "https://watch.example.com/page" },
      },
      querySelectorAll: (selector) => {
        if (
          selector.includes("iframe") ||
          selector.includes("link[href]") ||
          selector.includes("ld+json") ||
          selector === "meta"
        ) {
          return [];
        }
        return [
          { tagName: "VIDEO", getAttribute: () => "clip.mp4" },
          { tagName: "IMG", getAttribute: () => "javascript:alert(1)" },
        ];
      },
    };
    const result = collectMediaEvidence(doc);
    const urls = result.evidence.map((item) => item.url);
    assert.ok(urls.includes("https://cdn.example.com/media/clip.mp4"));
    assert.ok(!urls.includes("https://watch.example.com/clip.mp4"));
    assert.ok(!urls.includes("clip.mp4"));
    assert.ok(!urls.some((item) => item.startsWith("javascript:")));
    assert.equal(result.nativeCommand, null);
    const pageOnly = {
      location: { href: "https://watch.example.com/dir/page" },
      querySelectorAll: (selector) => {
        if (
          selector.includes("iframe") ||
          selector.includes("link[href]") ||
          selector.includes("ld+json") ||
          selector === "meta"
        ) {
          return [];
        }
        return [{ tagName: "VIDEO", getAttribute: () => "clip.mp4" }];
      },
    };
    const joined = collectMediaEvidence(pageOnly).evidence.map((item) => item.url);
    assert.ok(joined.includes("https://watch.example.com/dir/clip.mp4"));
    const blankSrc = {
      location: { href: "https://watch.example.com/page" },
      querySelectorAll: (selector) => {
        if (
          selector.includes("iframe") ||
          selector.includes("link[href]") ||
          selector.includes("ld+json") ||
          selector === "meta"
        ) {
          return [];
        }
        return [{ tagName: "VIDEO", getAttribute: () => "   " }];
      },
    };
    assert.equal(collectMediaEvidence(blankSrc).evidence.length, 0);
    const noBase = {
      querySelectorAll: (selector) => {
        if (
          selector.includes("iframe") ||
          selector.includes("link[href]") ||
          selector.includes("ld+json") ||
          selector === "meta"
        ) {
          return [];
        }
        return [
          { tagName: "VIDEO", getAttribute: () => "clip.mp4" },
          { tagName: "IMG", getAttribute: () => "http://[" },
        ];
      },
    };
    const raw = collectMediaEvidence(noBase).evidence.map((item) => item.url);
    assert.ok(raw.includes("clip.mp4"));
    assert.ok(raw.includes("http://["));
  });

  it("classifies video source, amp-img, data-src, and twitter:player", () => {
    const doc = {
      location: { href: "https://example.com/amp" },
      querySelectorAll: (selector) => {
        if (selector.includes("iframe") || selector.includes("link[href]") || selector.includes("ld+json")) {
          return [];
        }
        if (selector === "meta") {
          return [
            {
              getAttribute: (name) =>
                name === "name"
                  ? "twitter:player"
                  : name === "content"
                    ? "https://cdn.example.com/player.html"
                    : null,
            },
          ];
        }
        return [
          {
            tagName: "SOURCE",
            parentElement: { tagName: "VIDEO" },
            getAttribute: (name) => {
              if (name === "src") return "https://cdn.example.com/fallback.js";
              if (name === "type") return "video/mp4";
              return null;
            },
          },
          {
            tagName: "SOURCE",
            parentElement: { tagName: "VIDEO" },
            getAttribute: (name) =>
              name === "src" ? "https://cdn.example.com/via-source.mp4" : null,
          },
          {
            tagName: "SOURCE",
            parentElement: { tagName: "VIDEO" },
            getAttribute: (name) => {
              if (name === "src") return "https://cdn.example.com/plain-live";
              if (name === "type") return "application/vnd.apple.mpegurl";
              return null;
            },
          },
          {
            tagName: "AMP-IMG",
            getAttribute: (name) =>
              name === "src" ? "https://cdn.example.com/amp.png" : name === "data-src" ? "https://cdn.example.com/lazy.png" : null,
          },
        ];
      },
    };
    const result = collectMediaEvidence(doc);
    const byUrl = Object.fromEntries(result.evidence.map((item) => [item.url, item.kind]));
    assert.equal(byUrl["https://cdn.example.com/via-source.mp4"], "video");
    assert.equal(byUrl["https://cdn.example.com/fallback.js"], undefined);
    assert.equal(byUrl["https://cdn.example.com/plain-live"], "live_stream");
    assert.equal(byUrl["https://cdn.example.com/amp.png"], "image");
    assert.equal(byUrl["https://cdn.example.com/lazy.png"], "image");
    assert.equal(byUrl["https://cdn.example.com/player.html"], "video");
    assert.equal(result.nativeCommand, null);
  });

  it("collects iframe and link preload media", () => {
    const doc = {
      location: { href: "https://example.com/page" },
      querySelectorAll: (selector) => {
        if (selector.includes("iframe")) {
          return [
            { getAttribute: (name) => (name === "src" ? "https://cdn.example.com/live.m3u8" : null) },
            { getAttribute: (name) => (name === "src" ? "https://cdn.example.com/embed.js" : null) },
            { getAttribute: (name) => (name === "src" ? "https://cdn.example.com/embed.js/" : null) },
            { getAttribute: (name) => (name === "data" ? "https://cdn.example.com/object.js" : null) },
          ];
        }
        if (selector.includes("a[href]")) {
          return [
            {
              getAttribute: (name) =>
                name === "href" ? "https://cdn.example.com/classic.m3u" : null,
            },
            {
              getAttribute: (name) =>
                name === "href" ? "https://cdn.example.com/slash.m3u8/" : null,
            },
            {
              getAttribute: (name) =>
                name === "href" ? "https://cdn.example.com/icon.svg" : null,
            },
            {
              getAttribute: (name) =>
                name === "href" ? "https://cdn.example.com/slash.svg/" : null,
            },
          ];
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
                if (name === "href") return "https://cdn.example.com/bare.mp4";
                if (name === "rel") return "preload";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/app.js";
                if (name === "rel") return "modulepreload";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/boot.js";
                if (name === "as") return "script";
                if (name === "rel") return "preload";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/player.js";
                if (name === "as") return "video";
                if (name === "rel") return "preload";
                if (name === "type") return "video/mp4";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/player.js/";
                if (name === "as") return "video";
                if (name === "rel") return "preload";
                if (name === "type") return "video/mp4";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/playlist.json";
                if (name === "type") return "application/vnd.apple.mpegurl";
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
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/alt.mpd";
                if (name === "type") return "application/dash+xml";
                return null;
              },
            },
            {
              getAttribute: (name) => {
                if (name === "href") return "https://cdn.example.com/plain-live";
                if (name === "type") return "application/vnd.apple.mpegurl;charset=utf-8";
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
    const byUrl = Object.fromEntries(result.evidence.map((item) => [item.url, item.kind]));
    assert.ok(urls.includes("https://cdn.example.com/live.m3u8"));
    assert.ok(urls.includes("https://cdn.example.com/classic.m3u"));
    assert.ok(urls.includes("https://cdn.example.com/slash.m3u8/"));
    assert.ok(urls.includes("https://cdn.example.com/icon.svg"));
    assert.ok(urls.includes("https://cdn.example.com/slash.svg/"));
    assert.equal(byUrl["https://cdn.example.com/icon.svg"], "unknown");
    assert.equal(byUrl["https://cdn.example.com/slash.svg/"], "unknown");
    assert.ok(!urls.includes("https://cdn.example.com/embed.js"));
    assert.ok(!urls.includes("https://cdn.example.com/embed.js/"));
    assert.ok(!urls.includes("https://cdn.example.com/object.js"));
    assert.ok(urls.includes("https://cdn.example.com/pre.mp4"));
    assert.ok(urls.includes("https://cdn.example.com/bare.mp4"));
    assert.ok(!urls.includes("https://cdn.example.com/app.js"));
    assert.ok(!urls.includes("https://cdn.example.com/boot.js"));
    assert.ok(!urls.includes("https://cdn.example.com/player.js"));
    assert.ok(!urls.includes("https://cdn.example.com/player.js/"));
    assert.ok(urls.includes("https://cdn.example.com/playlist.json"));
    assert.equal(byUrl["https://cdn.example.com/playlist.json"], "live_stream");
    assert.ok(urls.includes("https://cdn.example.com/still.png"));
    assert.ok(urls.includes("https://cdn.example.com/alt.mpd"));
    assert.ok(urls.includes("https://cdn.example.com/plain-live"));
    assert.equal(byUrl["https://cdn.example.com/alt.mpd"], "live_stream");
    assert.equal(byUrl["https://cdn.example.com/plain-live"], "live_stream");
    assert.equal(byUrl["https://cdn.example.com/pre.mp4"], "video");
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
