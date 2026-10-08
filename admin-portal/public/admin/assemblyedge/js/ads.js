/* MajorityIQ — Google Political Ads Transparency (static JSON) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.adsData = null;
  AE.adsLoadError = null;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function formatUsd(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return "$" + Math.round(n).toLocaleString("en-US");
  }

  function weeklyBars(weekly, cls) {
    if (!weekly || !weekly.length) return `<span class="muted">No weekly rows</span>`;
    const vals = weekly.map((w) => Number(w.spend_usd) || 0);
    const max = Math.max(...vals, 1);
    const w = 280 / vals.length;
    const bars = vals
      .map((v, i) => {
        const h = Math.max(2, (v / max) * 44);
        const x = i * w + 2;
        return `<rect x="${x}" y="${48 - h}" width="${Math.max(4, w - 4)}" height="${h}" class="${cls || "bar-fill"}" rx="1">
          <title>${esc(weekly[i].week_start)}: ${formatUsd(v)} (Google weekly Spend_USD)</title></rect>`;
      })
      .join("");
    return `<svg class="ads-weekly-chart" viewBox="0 0 280 52" width="280" height="52" aria-hidden="true">${bars}</svg>`;
  }

  AE.ads.renderPanel = function (districtId) {
    const el = document.getElementById("ads-panel");
    if (!el) return;
    const dist = AE.adsData && AE.adsData.districts && AE.adsData.districts[districtId];
    const meta = AE.adsData || {};
    const asOf = meta.as_of_pt || "—";
    const note =
      (dist && dist.note) ||
      "Google ads only — Meta (Facebook/Instagram) not included; Meta Ad Library report can be added manually.";

    if (AE.adsLoadError) {
      el.innerHTML = `<div class="empty-state"><h3>Ad data unavailable</h3><p>${esc(AE.adsLoadError)}</p></div>`;
      return;
    }
    if (!dist || !dist.has_matched_ads) {
      el.innerHTML = `<div class="empty-state"><h3>No matched Google ads</h3>
        <p>No advertisers in the Google Political Ads Transparency bundle matched this district (candidate committees, CAL-ACCESS IE names, or curated IE labels).</p>
        <p class="money-source-note">${esc(note)}</p>
        <p class="money-source-note">Bundle as-of (PT): <strong>${esc(asOf)}</strong></p></div>`;
      return;
    }

    const sides = dist.by_side || {};
    const sideBlocks = ["R", "D", "IE"]
      .filter((s) => sides[s] && sides[s].advertisers && sides[s].advertisers.length)
      .map((s) => {
        const block = sides[s];
        const label = s === "IE" ? "Independent / IE (Google advertiser match)" : s === "R" ? "Republican-side" : "Democratic-side";
        const rows = block.advertisers
          .slice(0, 6)
          .map(
            (a) => `<li><a href="${esc(a.transparency_url)}" target="_blank" rel="noopener noreferrer">${esc(a.advertiser_name)}</a>
              · cycle total ${formatUsd(a.total_spend_usd)} <span class="chip chip-live">Google</span></li>`
          )
          .join("");
        return `<div class="card" style="margin-top:12px">
          <h4 class="card-title">${label}</h4>
          ${weeklyBars(block.weekly_total, s === "D" ? "bar-dem" : s === "R" ? "bar-rep" : "bar-ie")}
          <p class="money-source-note">Weekly spend (Google Spend_USD per week_start) — summed matched advertisers on this side.</p>
          <ul class="brief-bullets">${rows}</ul>
        </div>`;
      })
      .join("");

    const top = (dist.top_advertisers || [])
      .slice(0, 8)
      .map(
        (a) => `<tr>
          <td><a href="${esc(a.transparency_url)}" target="_blank" rel="noopener noreferrer">${esc(a.advertiser_name)}</a></td>
          <td class="mono">${formatUsd(a.total_spend_usd)}</td>
          <td>${esc((a.match_reasons || []).join(", "))}</td>
          <td class="mono">${esc(a.first_seen || "—")} → ${esc(a.last_seen || "—")}</td>
        </tr>`
      )
      .join("");

    el.innerHTML = `
      <div class="card">
        <h3 class="card-title">Google political ads <span class="chip chip-live">Google Transparency</span></h3>
        <p class="money-source-note">
          As-of (PT): <strong>${esc(asOf)}</strong>
          · Source: <a href="https://storage.googleapis.com/political-csv/google-political-ads-transparency-bundle.zip" target="_blank" rel="noopener noreferrer">Political Ads Transparency bundle</a>
          (no login). ${esc(note)}
        </p>
        ${sideBlocks || weeklyBars(dist.weekly_total)}
        <h4 class="card-title" style="margin-top:16px">Top matched advertisers</h4>
        <table class="money-table">
          <thead><tr><th>Advertiser</th><th>Cycle total (USD)</th><th>Match</th><th>First / last week</th></tr></thead>
          <tbody>${top}</tbody>
        </table>
      </div>`;
  };

  AE.ads.load = function () {
    AE.adsData = null;
    AE.adsLoadError = null;
    return fetch("data/ads/latest/ads-by-district.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.adsData = json;
        AE.adsLoadError = null;
      })
      .catch((err) => {
        AE.adsData = null;
        AE.adsLoadError = String(err && err.message ? err.message : err);
      });
  };
})();
