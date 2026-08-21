import { collectFromActiveTab, submitToWorker, activeTabLocator, loadWorkerToken, saveWorkerToken } from "./capture.js";

const SURFACE = "chromium";
const button = document.getElementById("send");
const status = document.getElementById("status");
const tokenInput = document.getElementById("token");

const stored = await loadWorkerToken();
if (tokenInput && stored) {
  tokenInput.value = stored;
  if (status) {
    status.textContent = "Token saved. Send is one tap.";
  }
}

button?.addEventListener("click", async () => {
  try {
    const token = tokenInput?.value?.trim() || "";
    if (!token) {
      status.textContent = "Paste the worker token once to enable one-tap capture.";
      return;
    }
    await saveWorkerToken(token);
    const page = await collectFromActiveTab();
    const locator = (await activeTabLocator()) || page.pageUrl;
    if (!locator) {
      status.textContent = "No page URL is available.";
      return;
    }
    status.textContent = `Captured ${page.evidence.length} page URL(s).`;
    await submitToWorker("http://127.0.0.1:8765", token, locator, SURFACE, page.evidence);
    status.textContent = "Submitted to the local worker.";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Capture failed.";
  }
});
