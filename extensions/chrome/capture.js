/**
 * Browser capture helper. Collects page evidence only.
 * Never becomes a generic native command runner.
 */
export function collectMediaEvidence(doc) {
  const urls = [];
  const push = (value, kind) => {
    if (typeof value === "string" && value && !value.startsWith("javascript:")) {
      urls.push({ url: value, kind });
    }
  };
  doc.querySelectorAll?.("video[src], audio[src], img[src], source[src]").forEach((el) => {
    const kind =
      el.tagName === "VIDEO" ? "video" : el.tagName === "AUDIO" ? "audio" : "image";
    push(el.getAttribute("src"), kind);
  });
  const ogImage = doc.querySelector?.('meta[property="og:image"]')?.getAttribute("content");
  push(ogImage, "image");
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

export async function submitToWorker(baseUrl, token, locator, surface = "chromium") {
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
    }),
  });
  if (!response.ok) {
    throw new Error(`Worker rejected capture (${response.status})`);
  }
  return response.json();
}
