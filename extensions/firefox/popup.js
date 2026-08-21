import { collectMediaEvidence, submitToWorker, activeTabLocator } from "./capture.js";

const SURFACE = "firefox";
const button = document.getElementById("send");
const status = document.getElementById("status");
const tokenInput = document.getElementById("token");

button?.addEventListener("click", async () => {
  try {
    const evidence = collectMediaEvidence(document);
    status.textContent = `Captured ${evidence.evidence.length} local preview URL(s).`;
    const locator = (await activeTabLocator()) || evidence.pageUrl;
    if (!locator) {
      status.textContent = "No page URL is available.";
      return;
    }
    await submitToWorker("http://127.0.0.1:8765", tokenInput.value, locator, SURFACE, evidence.evidence);
    status.textContent = "Submitted to the local worker.";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Capture failed.";
  }
});
