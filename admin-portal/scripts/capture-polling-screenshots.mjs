#!/usr/bin/env node
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const OUT = "/opt/cursor/artifacts/screenshots";
const BASE = "http://127.0.0.1:8765/admin/assemblyedge";

mkdirSync(OUT, { recursive: true });

const testPoll = [
    {
      id: 999,
      district_id: "ad-7",
      district_code: "AD-7",
      pollster: "TEST DATA pollster",
      sponsor: "TEST campaign memo",
      sponsor_type: "campaign",
      sponsor_party: "R",
      field_start: "2026-09-20",
      field_end: "2026-10-01",
      sample_n: 450,
      population: "LV",
      moe_pct: 4.5,
      undecided_pct: 6,
      toplines: [
        { name: "Josh Hoover", party: "R", pct: 47 },
        { name: "Amy L. Slavensky", party: "D", pct: 46 },
      ],
      visibility: "private",
      verified_by: "screenshot test only",
    },
  ];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

await page.addInitScript((poll) => {
  const origLoad = () => Promise.resolve();
  window.__TEST_INTERNAL_POLLS__ = poll;
  window.addEventListener("DOMContentLoaded", () => {
    setTimeout(() => {
      window.AE = window.AE || {};
      window.AE.pollingInternal = window.__TEST_INTERNAL_POLLS__;
    }, 0);
  });
}, testPoll);

await page.goto(`${BASE}/index.html`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
await page.click('button[data-page="polling"]');
await page.waitForSelector("#polling-infographic .poll-row");

await page.evaluate(() => {
  window.AE.pollingInternal = window.__TEST_INTERNAL_POLLS__ || [
    {
      id: 999,
      district_id: "ad-7",
      district_code: "AD-7",
      pollster: "TEST DATA pollster",
      sponsor: "TEST campaign memo",
      sponsor_type: "campaign",
      sponsor_party: "R",
      field_start: "2026-09-20",
      field_end: "2026-10-01",
      sample_n: 450,
      population: "LV",
      moe_pct: 4.5,
      undecided_pct: 6,
      toplines: [
        { name: "Josh Hoover", party: "R", pct: 47 },
        { name: "Amy L. Slavensky", party: "D", pct: 46 },
      ],
      visibility: "private",
      verified_by: "screenshot test only",
    },
  ];
  const btn = document.querySelector('button[data-page="portfolio"]');
  btn?.click();
  setTimeout(() => document.querySelector('button[data-page="polling"]')?.click(), 100);
});
await page.waitForTimeout(800);

await page.waitForTimeout(400);
await page.screenshot({ path: join(OUT, "majorityiq-polling-internal-test.png"), fullPage: true });

await page.evaluate(async () => {
  try {
    const r = await fetch("data/polls/leads.json");
    if (r.ok) window.AE.pollingLeads = await r.json();
  } catch {
    /* ignore */
  }
  document.querySelector('button[data-page="portfolio"]')?.click();
  setTimeout(() => document.querySelector('button[data-page="polling"]')?.click(), 150);
});
await page.waitForTimeout(900);
await page.evaluate(() => {
  document.querySelector(".poll-leads-admin")?.scrollIntoView({ block: "center" });
});
await page.waitForTimeout(200);
await page.screenshot({ path: join(OUT, "majorityiq-polling-leads.png"), fullPage: false });

await page.goto(`${BASE}/polls-admin-preview.html`, { waitUntil: "networkidle" });
await page.screenshot({ path: join(OUT, "majorityiq-polls-admin-form.png"), fullPage: true });

await browser.close();
console.log("Saved screenshots to", OUT);
