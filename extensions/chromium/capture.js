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
  const push = (value, kind) => {
    if (
      typeof value === "string" &&
      value &&
      !value.toLowerCase().startsWith("javascript:") &&
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
    if (typeof node.contentUrl === "string") {
      push(node.contentUrl, "video");
    }
    if (typeof node.embedUrl === "string") {
      push(node.embedUrl, "video");
    }
    Object.values(node).forEach((value) => walkJsonLd(value));
  };
  root.querySelectorAll?.("video, audio, img, source, track").forEach((el) => {
    const tag = el.tagName;
    const kind =
      tag === "VIDEO" ? "video" : tag === "AUDIO" ? "audio" : tag === "TRACK" ? "subtitle" : "image";
    push(el.getAttribute?.("src"), kind);
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
    "twitter:player:stream": "video",
    "og:audio": "audio",
    "og:audio:url": "audio",
  };
  root.querySelectorAll?.("meta").forEach((el) => {
    const key = el.getAttribute?.("property") || el.getAttribute?.("name");
    const kind = metaKind[key];
    if (kind) {
      push(el.getAttribute?.("content"), kind);
    }
  });
  root.querySelectorAll?.('script[type="application/ld+json"]').forEach((el) => {
    const raw = el.textContent || el.innerText || "";
    try {
      walkJsonLd(JSON.parse(raw));
    } catch {
      /* ignore malformed JSON-LD */
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
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/jobs`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      locator,
      surface,
      local_user_confirmed: true,
      wait: false,
      evidence,
    }),
  });
  if (!response.ok) {
    throw new Error(`Worker rejected capture (${response.status})`);
  }
  return response.json();
}
