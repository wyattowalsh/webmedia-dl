/**
 * Browser capture helper. Collects page evidence only.
 * Never becomes a generic native command runner.
 */
export function collectMediaEvidence(doc) {
  const urls = [];
  const seen = new Set();
  const push = (value, kind) => {
    if (typeof value === "string" && value && !value.startsWith("javascript:") && !seen.has(value)) {
      seen.add(value);
      urls.push({ url: value, kind });
    }
  };
  doc.querySelectorAll?.("video, audio, img, source").forEach((el) => {
    const kind =
      el.tagName === "VIDEO" ? "video" : el.tagName === "AUDIO" ? "audio" : "image";
    push(el.getAttribute?.("src"), kind);
    push(el.currentSrc, kind);
    push(el.getAttribute?.("poster"), "image");
    const srcset = el.getAttribute?.("srcset");
    if (srcset) {
      srcset.split(",").forEach((part) => push(part.trim().split(/\s+/)[0], kind));
    }
  });
  const ogImage = doc.querySelector?.('meta[property="og:image"]')?.getAttribute("content");
  push(ogImage, "image");
  const ogVideo = doc.querySelector?.('meta[property="og:video"]')?.getAttribute("content");
  push(ogVideo, "video");
  return {
    pageUrl: doc.location?.href ?? null,
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
      evidence,
    }),
  });
  if (!response.ok) {
    throw new Error(`Worker rejected capture (${response.status})`);
  }
  return response.json();
}
