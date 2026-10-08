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

const adminHtml = renderPollsAdminPage({
  csrfToken: "screenshot-fixture",
  username: "desk",
  deskPrefix: "/admin/assemblyedge",
});
writeFileSync(CAPTURE_HTML, adminHtml, "utf8");

const browser = await chromium.launch({ headless: true });

async function shotAdmin(width, name) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.route("**/api/polls/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, polls: [], leads: [] }),
    }),
  );
  await page.goto(`${BASE}/_capture-polls-admin.html`, { waitUntil: "networkidle" });
  await page.waitForSelector("#candidate-rows .candidate-row");
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(OUT, name), fullPage: true });
  await page.close();
}

await shotAdmin(1280, "majorityiq-polls-admin-desktop.png");
await shotAdmin(390, "majorityiq-polls-admin-mobile.png");

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`${BASE}/index.html`, { waitUntil: "networkidle" });
await page.evaluate(() => {
  window.AE.pollingDesk.adminSession = true;
});
await page.waitForTimeout(1500);
await page.click('button[data-page="polling"]');
await page.waitForSelector("#polling-infographic .poll-row");
await page.evaluate(async () => {
  try {
    const r = await fetch("data/polls/leads.json");
    if (r.ok) window.AE.pollingLeads = await r.json();
  } catch {
    /* ignore */
  }
  document.querySelector('button[data-page="portfolio"]')?.click();
});
await page.waitForTimeout(200);
await page.click('button[data-page="polling"]');
await page.waitForTimeout(400);
await page.evaluate(() => {
  document.querySelector(".poll-leads-admin")?.scrollIntoView({ block: "start" });
});
await page.waitForTimeout(200);
await page.screenshot({ path: join(OUT, "majorityiq-polling-leads.png"), fullPage: true });

await browser.close();
console.log("Saved screenshots to", OUT);
