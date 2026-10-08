#!/usr/bin/env node
/** Screenshot helper — writes to /opt/cursor/artifacts/screenshots (not committed). */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";
import { renderPollsAdminPage } from "../src/assemblyedge-polls-admin.js";

const OUT = "/opt/cursor/artifacts/screenshots";
const BASE = "http://127.0.0.1:8765/admin/assemblyedge";
const CAPTURE_HTML = "/workspace/admin-portal/public/admin/assemblyedge/_capture-polls-admin.html";

mkdirSync(OUT, { recursive: true });

writeFileSync(
  CAPTURE_HTML,
  renderPollsAdminPage({
    csrfToken: "screenshot-fixture",
    username: "desk",
    deskPrefix: "/admin/assemblyedge",
  }),
  "utf8",
);

const browser = await chromium.launch({ headless: true });

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.route("**/api/csrf**", (route) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ csrf: "screenshot" }) }),
);
await page.route("**/api/polls/**", (route) => {
  const url = route.request().url();
  if (url.includes("/api/polls/leads")) {
    return route.fulfill({ status: 401, contentType: "application/json", body: "{}" });
  }
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ok: true, polls: [] }),
  });
});
await page.goto(`${BASE}/index.html`, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.AE && window.AE.pollingReleased && window.AE.pollingData);
await page.evaluate(async () => {
  if (window.AE.pollingDesk.load) await window.AE.pollingDesk.load();
  window.AE.pollingDesk.adminSession = true;
});
await page.click('button[data-page="polling"]');
await page.waitForSelector("#polling-infographic .poll-row");
await page.waitForSelector(".poll-leads-list li", { timeout: 8000 });
await page.evaluate(() => document.querySelector(".poll-leads-admin")?.scrollIntoView({ block: "center" }));
await page.waitForTimeout(300);
await page.screenshot({ path: join(OUT, "majorityiq-polling-ad36-released.png"), fullPage: true });

await page.click('button[data-district-open="ad-36"]');
await page.waitForTimeout(800);
await page.waitForSelector("#district-polling-strip");
await page.evaluate(() => {
  document.getElementById("district-polling-strip")?.scrollIntoView({ block: "center" });
});
await page.screenshot({ path: join(OUT, "majorityiq-district-ad36-polling.png"), fullPage: false });

await browser.close();
console.log("Saved screenshots to", OUT);
