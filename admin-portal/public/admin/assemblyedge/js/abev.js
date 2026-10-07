/* MajorityIQ — ballot returns (ABEV-style) loader + panels */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.abev = AE.abev || {};
  AE.abevData = null;
  AE.abevLoadError = null;

  const PARTY_COLORS = {
    dem: "#5c8fd4",
    rep: "#c45c5c",
    npp: "#8a919e",
    aip: "#6b7280",
    grn: "#3d9a6a",
    lib: "#b8860b",
    other: "#4b5563",
  };

  AE.abev.districtRow = function (districtId) {
    const root = AE.abevData;
    if (!root || !Array.isArray(root.districts)) return null;
    return root.districts.find((d) => d.id === districtId) || null;
  };

  AE.abev.meta = function () {
    return AE.abevData || null;
  };

  AE.abev.load = function () {
    AE.abevData = null;
    AE.abevLoadError = null;
    return fetch("data/abev/latest/abev-by-district.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.abevData = json;
        AE.abevLoadError = null;
      })
      .catch((err) => {
        AE.abevData = null;
        AE.abevLoadError = String(err && err.message ? err.message : err);
      });
  };

  AE.abev.formatNumber = function (n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString("en-US");
  };

  AE.abev.formatPct = function (n, digits) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    const d = digits == null ? 1 : digits;
    return Number(n).toFixed(d) + "%";
  };

  function baseline(row, code) {
    const b = row && row.baselines;
    if (!b) return null;
    return b[code] || null;
  }

  AE.abev.partyBarHtml = function (parties, opts) {
    opts = opts || {};
    const minPct = opts.minPct != null ? opts.minPct : 0.5;
    if (!parties || !parties.length) return "";
    const segs = parties
      .filter((p) => p.pct != null && p.pct >= minPct)
      .map(
        (p) =>
          `<span class="abev-bar-seg party-${p.id}" style="width:${p.pct}%;background:${PARTY_COLORS[p.id] || "#666"}" title="${p.label} ${p.pct}%"></span>`
      )
      .join("");
    return `<div class="abev-bar-track" role="img" aria-label="Party mix of mail ballot returns">${segs}</div>`;
  };

  AE.abev.progressStripHtml = function (opts) {
    opts = opts || {};
    const pctLive = opts.pctLive;
    const pctBaseline = opts.pctBaseline;
    const label = opts.label || "Mail ballots returned";
    const liveVal = pctLive != null ? AE.abev.formatPct(pctLive, 1) : null;
    const bench = pctBaseline != null ? AE.abev.formatPct(pctBaseline, 1) : null;
    const fill = pctLive != null ? Math.min(100, pctLive) : 0;
    const marker =
      pctBaseline != null
        ? `<span class="abev-bench-marker" style="left:${Math.min(100, pctBaseline)}%" title="2024 general final: ${bench} of SOV registration"></span>`
        : "";
    const sub =
      pctLive != null
        ? `<span class="abev-strip-val">${liveVal}</span> of registration`
        : `<span class="abev-strip-gap">${opts.gapLabel || "Live returns pending"}</span>`;
    return `<div class="abev-progress-block">
      <div class="abev-progress-head"><span>${label}</span>${bench ? `<span class="abev-bench-label">2024 final ${bench}</span>` : ""}</div>
      <div class="abev-progress-track" aria-hidden="true">
        <span class="abev-progress-fill ${pctLive == null ? "is-gap" : ""}" style="width:${fill}%"></span>
        ${marker}
      </div>
      <div class="abev-progress-foot">${sub}</div>
    </div>`;
  };

  AE.abev.renderPanel = function (districtId, compact) {
    const row = AE.abev.districtRow(districtId);
    if (AE.abevLoadError) {
      return `<div class="empty-state demo-panel-empty"><h3>Ballot returns unavailable</h3><p>${AE.abevLoadError}</p></div>`;
    }
    if (!row) {
      return `<div class="empty-state demo-panel-empty"><h3>No ABEV row</h3><p>Missing beachhead entry in abev JSON.</p></div>`;
    }

    const live = row.live || {};
    const g24 = baseline(row, "g24");
    const g22 = baseline(row, "g22");
    const reg = row.registration_current;
    const liveChip =
      live.status === "not_published" || live.returned == null
        ? `<span class="chip chip-gap">Live gap</span>`
        : `<span class="chip chip-live">Live feed</span>`;
    const histChip = `<span class="chip chip-live-weak">SWDB baseline</span>`;

    const strip = AE.abev.progressStripHtml({
      pctLive: live.pct_of_registration,
      pctBaseline: g24 && g24.vbm_pct_of_sov_registration,
      gapLabel: live.gap_label || "Live 2026 returns not published",
    });

    let partyHtml = "";
    if (g24 && g24.party_returns && g24.party_returns.length) {
      partyHtml = `<div class="abev-block">
        <h4 class="demo-block-title">2024 general — party mix of mail returns</h4>
        ${AE.abev.partyBarHtml(g24.party_returns)}
        <ul class="demo-legend-list">${g24.party_returns
          .filter((p) => p.pct != null && p.pct >= 0.5)
          .map(
            (p) =>
              `<li><span>${p.label}</span><span class="demo-legend-val">${p.pct}% · ${AE.abev.formatNumber(p.count)}</span></li>`
          )
          .join("")}</ul>
      </div>`;
    }

    const pace = row.baselines && row.baselines.pace_note ? `<p class="demo-footnote">${row.baselines.pace_note}</p>` : "";

    const stats = [];
    if (g24) {
      stats.push(
        `<div class="stat-pill"><div class="label">2024 mail returned</div><div class="value">${AE.abev.formatNumber(g24.vbm_returned)}</div></div>`
      );
      stats.push(
        `<div class="stat-pill"><div class="label">2024 mail / SOV reg</div><div class="value">${AE.abev.formatPct(g24.vbm_pct_of_sov_registration, 1)}</div></div>`
      );
    }
    if (g22 && !compact) {
      stats.push(
        `<div class="stat-pill"><div class="label">2022 mail / SOV reg</div><div class="value">${AE.abev.formatPct(g22.vbm_pct_of_sov_registration, 1)}</div></div>`
      );
    }

    const meta = AE.abev.meta();
    const updated = meta && meta.updated_at ? meta.updated_at.slice(0, 10) : "—";
    const regLine = reg
      ? `Registration (SOS ROR): ${AE.abev.formatNumber(reg)} · ${row.registration_current_source || "CA SOS"}`
      : "Registration denominator from demography bundle when available.";

    return `<div class="abev-panel demo-panel">
      <div class="demo-panel-head">
        <h3 class="card-title" style="margin:0">Ballot returns ${liveChip} ${histChip}</h3>
      </div>
      <p class="demo-source-line">JSON built ${updated} · SWDB All_VBM + county SOV · ${regLine}</p>
      ${strip}
      <div class="demo-stat-grid">${stats.join("")}</div>
      ${partyHtml}
      ${pace}
      <p class="demo-footnote">${live.detail || live.gap_label || ""} Public aggregates only — not a voter file or chase list.</p>
      <p class="demo-footnote">Refresh: <code>data/abev/README.md</code></p>
    </div>`;
  };

  AE.abev.renderPortfolioStrip = function () {
    const root = AE.abevData;
    if (AE.abevLoadError || !root || !root.districts) {
      return `<p class="intel-teaser-desc">${AE.abevLoadError || "Loading ballot return data…"}</p>`;
    }
    const cards = root.districts
      .slice()
      .sort((a, b) => a.code.localeCompare(b.code))
      .map((row) => {
        const g24 = baseline(row, "g24");
        const live = row.live || {};
        const code = row.code;
        const bench = g24 ? AE.abev.formatPct(g24.vbm_pct_of_sov_registration, 0) : "—";
        const gap = live.returned == null;
        const fill = gap ? 0 : Math.min(100, live.pct_of_registration || 0);
        return `<article class="abev-portfolio-card ${gap ? "has-gap" : ""}" data-district-abev="${row.id}">
          <div class="abev-portfolio-code">${code}</div>
          <div class="abev-progress-track abev-progress-track-sm" aria-hidden="true">
            <span class="abev-progress-fill is-gap" style="width:${fill}%"></span>
            ${g24 ? `<span class="abev-bench-marker" style="left:${Math.min(100, g24.vbm_pct_of_sov_registration)}%"></span>` : ""}
          </div>
          <div class="abev-portfolio-meta">
            ${gap ? `<span class="chip chip-gap">Live pending</span>` : `<span class="chip chip-live">Live</span>`}
            <span class="abev-portfolio-bench" title="2024 general final mail return rate">2024 ${bench}</span>
          </div>
        </article>`;
      })
      .join("");
    return `<div class="abev-portfolio-strip" role="list">${cards}</div>
      <p style="margin:10px 0 0;font-size:12px;color:var(--text-dim)">Marker = 2024 general final mail returns as % of SOV registration. Live 2026 AD feeds not published — gaps labeled.</p>`;
  };
})();
