import { collectFromActiveTab, submitToWorker, activeTabLocator } from "./capture.js";

const SURFACE = "firefox";
const button = document.getElementById("send");
const status = document.getElementById("status");
const tokenInput = document.getElementById("token");

button?.addEventListener("click", async () => {
  try {
    const page = await collectFromActiveTab();
    const locator = (await activeTabLocator()) || page.pageUrl;
    if (!locator) {
      status.textContent = "No page URL is available.";
      return;
    }
    status.textContent = `Captured ${page.evidence.length} page URL(s).`;
    await submitToWorker("http://127.0.0.1:8765", tokenInput.value, locator, SURFACE, page.evidence);
    status.textContent = "Submitted to the local worker.";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Capture failed.";
  }
});
