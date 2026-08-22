/**
 * Browser capture helper. Collects page media evidence only.
 * Never becomes a generic native command runner.
 */

export function collectMediaEvidence(doc) {
  return pageCollector(doc);
}

/** Self-contained so MV3 `scripting.executeScript({ func })` can serialize it. */
export function pageCollector(doc) {
  const root = doc && typeof doc.querySelectorAll === "function" ? doc : globalThis.document;
  const urls = [];
  const seen = new Set();
  const blockedScheme =
    /^(javascript|data|blob|file|about|chrome|chrome-extension):/i;
  const push = (value, kind) => {
    if (
      typeof value === "string" &&
      value &&
      !blockedScheme.test(value.trim()) &&
      !seen.has(value)
    ) {
      seen.add(value);
      urls.push({ url: value, kind });
    }
  };
  const walkJsonLd = (node) => {
    if (Array.isArray(node)) {
      node.forEach((item) => walkJsonLd(item));
      return;
    }
    if (!node || typeof node !== "object") {
      return;
    }
    const jsonLdType = String(node["@type"] || node.type || "").toLowerCase();
    const jsonLdKind = jsonLdType.includes("audio")
      ? "audio"
      : jsonLdType.includes("image")
        ? "image"
        : "video";
    const pushJsonLdUrl = (value, kind) => {
      if (typeof value === "string") {
        push(value, kind);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach((item) => pushJsonLdUrl(item, kind));
        return;
      }
      if (value && typeof value === "object") {
        if (typeof value["@id"] === "string") {
          push(value["@id"], kind);
        } else if (typeof value.url === "string") {
          push(value.url, kind);
        }
      }
    };
    pushJsonLdUrl(node.contentUrl, jsonLdKind);
    pushJsonLdUrl(node.embedUrl, jsonLdKind);
    Object.values(node).forEach((value) => walkJsonLd(value));
  };
  const kindFromElement = (el) => {
    const tag = String(el.tagName || "").toUpperCase();
    const mime = (el.getAttribute?.("type") || "").toLowerCase();
    const parent = String(el.parentElement?.tagName || "").toUpperCase();
    if (tag === "TRACK") {
      return "subtitle";
    }
    if (mime.includes("mpegurl") || mime.includes("dash+xml")) {
      return "live_stream";
    }
    if (tag === "AUDIO" || tag === "AMP-AUDIO" || mime.startsWith("audio/")) {
      return "audio";
    }
    if (tag === "VIDEO" || tag === "AMP-VIDEO" || mime.startsWith("video/")) {
      return "video";
    }
    if (tag === "SOURCE") {
      if (parent === "AUDIO" || parent === "AMP-AUDIO") {
        return "audio";
      }
      if (parent === "VIDEO" || parent === "AMP-VIDEO") {
        return "video";
      }
      if (parent === "PICTURE") {
        return "image";
      }
    }
    return "image";
  };
  root
    .querySelectorAll?.(
      "video, audio, img, source, track, amp-img, amp-video, amp-audio, picture",
    )
    .forEach((el) => {
      const kind = kindFromElement(el);
      push(el.getAttribute?.("src"), kind);
      push(el.getAttribute?.("data-src"), kind);
      push(el.currentSrc, kind);
      push(el.getAttribute?.("poster"), "image");
      const srcset = el.getAttribute?.("srcset");
      if (srcset) {
        srcset.split(",").forEach((part) => push(part.trim().split(/\s+/)[0], kind));
      }
    });
  const metaKind = {
    "og:image": "image",
    "og:image:url": "image",
    "twitter:image": "image",
    "og:video": "video",
    "og:video:url": "video",
    "og:video:secure_url": "video",
    "twitter:player:stream": "video",
    "twitter:player": "video",
    "og:audio": "audio",
    "og:audio:url": "audio",
    "og:audio:secure_url": "audio",
  };
  root.querySelectorAll?.("meta").forEach((el) => {
    const key = el.getAttribute?.("property") || el.getAttribute?.("name");
    const kind = metaKind[key];
    if (kind) {
      push(el.getAttribute?.("content"), kind);
    }
  });
  root.querySelectorAll?.('script[type^="application/ld+json"]').forEach((el) => {
    const parseJsonLd = (raw) => {
      let unwrapped = String(raw || "").trim();
      if (unwrapped.startsWith("<!--")) {
        unwrapped = unwrapped.replace(/^<!--/, "").replace(/-->$/, "").trim();
      }
      if (unwrapped.startsWith("<![CDATA[")) {
        unwrapped = unwrapped.replace(/^<!\[CDATA\[/, "").replace(/\]\]>$/, "").trim();
      }
      const parseOnce = (value) => {
        try {
          walkJsonLd(JSON.parse(value));
          return true;
        } catch {
          return false;
        }
      };
      if (parseOnce(unwrapped)) {
        return;
      }
      const decoded = unwrapped
        .replace(/&quot;/gi, '"')
        .replace(/&#34;/g, '"')
        .replace(/&apos;/gi, "'")
        .replace(/&#39;/g, "'")
        .replace(/&lt;/gi, "<")
        .replace(/&gt;/gi, ">")
        .replace(/&amp;/gi, "&");
      if (decoded !== unwrapped) {
        parseOnce(decoded);
      }
    };
    const raw = el.textContent || el.innerText || "";
    parseJsonLd(raw);
  });
  root.querySelectorAll?.("iframe, embed, object").forEach((el) => {
    push(el.getAttribute?.("src") || el.getAttribute?.("data"), "video");
  });
  root.querySelectorAll?.("link[href]").forEach((el) => {
    const asAttr = (el.getAttribute?.("as") || "").toLowerCase();
    const rel = (el.getAttribute?.("rel") || "").toLowerCase();
    const mime = (el.getAttribute?.("type") || "").toLowerCase();
    if (
      asAttr === "video" ||
      asAttr === "audio" ||
      asAttr === "image" ||
      asAttr === "track" ||
      rel.includes("preload") ||
      mime.startsWith("video/") ||
      mime.startsWith("audio/") ||
      mime.startsWith("image/") ||
      mime.includes("mpegurl") ||
      mime.includes("dash+xml")
    ) {
      let kind = "video";
      if (mime.includes("mpegurl") || mime.includes("dash+xml")) {
        kind = "live_stream";
      } else if (asAttr === "audio" || mime.startsWith("audio/")) {
        kind = "audio";
      } else if (asAttr === "image" || mime.startsWith("image/")) {
        kind = "image";
      } else if (asAttr === "track") {
        kind = "subtitle";
      }
      push(el.getAttribute?.("href"), kind);
    }
  });
  root.querySelectorAll?.("a[href]").forEach((el) => {
    const href = el.getAttribute?.("href");
    if (
      typeof href === "string" &&
      /\.(mp4|webm|mkv|mov|m4v|mp3|m4a|aac|flac|wav|ogg|opus|jpg|jpeg|png|gif|webp|avif|pdf|vtt|srt|m3u8|mpd)(\?|#|$)/i.test(
        href,
      )
    ) {
      push(href, "unknown");
    }
  });
  return {
    pageUrl: root.location?.href ?? null,
    evidence: urls,
    nativeCommand: null,
  };
}

export async function activeTabLocator() {
  const tabsApi = globalThis.chrome?.tabs ?? globalThis.browser?.tabs;
  if (!tabsApi?.query) {
    return null;
  }
  const tabs = await tabsApi.query({ active: true, currentWindow: true });
  return tabs[0]?.url ?? null;
}

export async function collectFromActiveTab() {
  const tabsApi = globalThis.chrome?.tabs ?? globalThis.browser?.tabs;
  const scripting = globalThis.chrome?.scripting ?? globalThis.browser?.scripting;
  if (!tabsApi?.query) {
    return pageCollector(globalThis.document);
  }
  const tabs = await tabsApi.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (scripting?.executeScript && tab?.id != null) {
    const injected = await scripting.executeScript({
      target: { tabId: tab.id },
      func: pageCollector,
    });
    const result = injected?.[0]?.result;
    if (result && Array.isArray(result.evidence)) {
      return result;
    }
  }
  return {
    pageUrl: tab?.url ?? null,
    evidence: [],
    nativeCommand: null,
  };
}

export async function submitToWorker(baseUrl, token, locator, surface = "chromium", evidence = []) {
  const auth = String(token || "").trim();
  if (!auth) {
    throw new Error("Worker token is required.");
  }
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/jobs`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${auth}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      locator,
      surface,
      local_user_confirmed: true,
      wait: false,
      intake_kind: "browser_evidence",
      evidence,
    }),
  });
  if (!response.ok) {
    throw new Error(`Worker rejected capture (${response.status})`);
  }
  return response.json();
}

export const WORKER_TOKEN_KEY = "webmediaDlWorkerToken";

function extensionStorage(area) {
  return area || globalThis.browser?.storage?.local || globalThis.chrome?.storage?.local || null;
}

export async function loadWorkerToken(area) {
  const api = extensionStorage(area);
  if (!api || typeof api.get !== "function") {
    return "";
  }
  try {
    const result = await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (value) => {
        if (settled) {
          return;
        }
        settled = true;
        resolve(value);
      };
      try {
        const maybe = api.get(WORKER_TOKEN_KEY, finish);
        if (maybe && typeof maybe.then === "function") {
          maybe.then(finish, reject);
        }
      } catch (error) {
        reject(error);
      }
    });
    if (!result || typeof result !== "object") {
      return "";
    }
    return String(result[WORKER_TOKEN_KEY] || "").trim();
  } catch {
    return "";
  }
}

export async function saveWorkerToken(token, area) {
  const value = String(token || "").trim();
  if (!value) {
    return;
  }
  const api = extensionStorage(area);
  if (!api || typeof api.set !== "function") {
    return;
  }
  const payload = { [WORKER_TOKEN_KEY]: value };
  if (api.set.length >= 2) {
    await new Promise((resolve) => api.set(payload, resolve));
    return;
  }
  await api.set(payload);
}
