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

  function formatWeekPt(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso + "T12:00:00Z");
      return d.toLocaleDateString("en-US", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso;
    }
  }

  function sideBarClass(side) {
    if (side === "R") return "ads-bar-rep";
    if (side === "D") return "ads-bar-dem";
    return "ads-bar-ie";
  }

  function weeklyChart(weekly, side) {
    if (!weekly || !weekly.length) {
      return `<p class="money-source-note">No weekly spend rows for this side.</p>`;
    }
    const vals = weekly.map((w) => Number(w.spend_usd) || 0);
    const max = Math.max(...vals, 1);
    const barCls = sideBarClass(side);
    const last = weekly[weekly.length - 1];
    const bars = weekly
      .map((w, i) => {
        const v = vals[i];
        const pct = Math.max(2, Math.round((v / max) * 100));
        const label = formatWeekPt(w.week_start);
        return `<div class="ads-weekly-bar" title="${esc(label)} (PT): ${formatUsd(v)} Google Spend_USD">
          <span class="ads-weekly-amt mono">${formatUsd(v)}</span>
          <div class="ads-weekly-bar-fill ${barCls}" style="height:${pct}%"></div>
          <span class="ads-weekly-wk">${esc(label)}</span>
        </div>`;
      })
      .join("");
    return `<div class="ads-weekly-wrap" role="img" aria-label="Weekly Google political ad spend">
      <div class="ads-weekly-bars">${bars}</div>
      <p class="ads-weekly-latest">Latest week (PT): <strong>${esc(formatWeekPt(last.week_start))}</strong> · <strong>${formatUsd(last.spend_usd)}</strong> <span class="muted">(Google Spend_USD)</span></p>
    </div>`;
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

    const gapNotes = (dist.candidate_google_gaps || [])
      .map((g) => `<li><strong>${esc(g.candidate)}</strong>: ${esc(g.note)}</li>`)
      .join("");

    const sides = dist.by_side || {};
    const sideBlocks = ["R", "D", "IE"]
      .filter((s) => sides[s] && sides[s].advertisers && sides[s].advertisers.length)
      .map((s) => {
        const block = sides[s];
        const label =
          s === "IE" ? "Independent / IE (Google advertiser match)" : s === "R" ? "Republican-side" : "Democratic-side";
        const rows = block.advertisers
          .slice(0, 6)
          .map(
            (a) => `<li><a href="${esc(a.transparency_url)}" target="_blank" rel="noopener noreferrer">${esc(a.advertiser_name)}</a>
              · cycle total ${formatUsd(a.total_spend_usd)} <span class="chip chip-live">Google</span></li>`
          )
          .join("");
        return `<div class="card ads-side-card">
          <h4 class="card-title">${label}</h4>
          ${weeklyChart(block.weekly_total, s)}
          <p class="money-source-note">Weekly spend summed across matched ${label.toLowerCase()} advertisers (Google-reported Spend_USD).</p>
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
        ${gapNotes ? `<div class="card" style="margin-top:12px;background:var(--surface-2)"><h4 class="card-title">Candidate Google gaps</h4><ul class="brief-bullets">${gapNotes}</ul></div>` : ""}
        <div class="ads-side-grid">${sideBlocks || weeklyChart(dist.weekly_total, "IE")}</div>
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
