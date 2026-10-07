/* AssemblyEdge — demography + registration loader (Focus drill panel) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.demography = AE.demography || {};
  AE.demographyData = null;
  AE.demographyLoadError = null;

  AE.demography.districtRow = function (districtId) {
    const root = AE.demographyData;
    if (!root || !Array.isArray(root.districts)) return null;
    return root.districts.find((d) => d.id === districtId) || null;
  };

  AE.demography.meta = function () {
    const root = AE.demographyData;
    if (!root) return null;
    return {
      updatedAt: root.updated_at,
      acs: root.sources && root.sources.acs,
      registration: root.sources && root.sources.registration,
    };
  };

  AE.demography.load = function () {
    AE.demographyData = null;
    AE.demographyLoadError = null;
    return fetch("data/demography/latest/demography-by-district.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.demographyData = json;
        AE.demographyLoadError = null;
      })
      .catch((err) => {
        AE.demographyData = null;
        AE.demographyLoadError = String(err && err.message ? err.message : err);
      });
  };

  AE.demography.formatNumber = function (n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString("en-US");
  };

  AE.demography.formatMoney = function (n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return "$" + Number(n).toLocaleString("en-US");
  };

  AE.demography.registrationBarHtml = function (parties) {
    if (!parties || !parties.length) return "";
    const colors = {
      dem: "#5c8fd4",
      rep: "#c45c5c",
      npp: "#8a919e",
      other: "#6b7280",
    };
    const segs = parties
      .filter((p) => p.pct != null && p.pct > 0)
      .map(
        (p) =>
          `<span class="demo-bar-seg reg-${p.id}" style="width:${p.pct}%;background:${colors[p.id] || "#666"}" title="${p.label} ${p.pct}%"></span>`
      )
      .join("");
    return `<div class="demo-bar-track" role="img" aria-label="Registration party mix">${segs}</div>`;
  };

  AE.demography.ageBarHtml = function (bands) {
    if (!bands || !bands.length) return "";
    const palette = ["#3d8bfd", "#5c8fd4", "#7aa2e3", "#b8860b", "#8a919e"];
    const segs = bands
      .map(
        (b, i) =>
          `<span class="demo-bar-seg" style="width:${b.pct}%;background:${palette[i % palette.length]}" title="${b.label} ${b.pct}%"></span>`
      )
      .join("");
    return `<div class="demo-bar-track demo-bar-track-thin" role="img" aria-label="Population by age band">${segs}</div>`;
  };

  AE.demography.renderPanel = function (districtId) {
    const row = AE.demography.districtRow(districtId);
    const meta = AE.demography.meta();
    if (AE.demographyLoadError) {
      return `<div class="empty-state demo-panel-empty"><h3>Demography unavailable</h3><p>${AE.demographyLoadError}</p></div>`;
    }
    if (!row) {
      return `<div class="empty-state demo-panel-empty"><h3>No demography row</h3><p>Missing beachhead entry in demography JSON.</p></div>`;
    }

    const acs = row.acs;
    const reg = row.registration;
    const acsIncomplete =
      !acs || !acs.population || !acs.age_bands || !acs.age_bands.length || row.acs_error;
    const regIncomplete = !reg || !reg.total;

    const acsChip = acsIncomplete
      ? `<span class="chip chip-demo">ACS fallback</span>`
      : `<span class="chip chip-live">Public ACS</span>`;
    const regChip = regIncomplete
      ? `<span class="chip chip-demo">Reg. incomplete</span>`
      : `<span class="chip chip-live-weak">SOS ROR</span>`;

    const acsAsOf =
      acs && acs.release_years
        ? `ACS ${acs.release_years} · ${acs.source_label || "Census ACS 5-year"}`
        : "ACS — source pending";
    const regAsOf =
      meta && meta.registration && meta.registration.as_of
        ? `Registration as of ${meta.registration.as_of} · ${meta.registration.source_label || "CA SOS"}`
        : "CA SOS registration";

    let statsHtml = "";
    if (acs && !acsIncomplete) {
      statsHtml += `<div class="demo-stat-grid">
        <div class="stat-pill"><div class="label">Population</div><div class="value">${AE.demography.formatNumber(acs.population)}</div></div>
        <div class="stat-pill"><div class="label">Median HH income</div><div class="value">${AE.demography.formatMoney(acs.median_household_income)}</div></div>
      </div>`;
    }

    let ageHtml = "";
    if (acs && acs.age_bands && acs.age_bands.length) {
      ageHtml = `<div class="demo-block">
        <h4 class="demo-block-title">Age bands</h4>
        ${AE.demography.ageBarHtml(acs.age_bands)}
        <ul class="demo-legend-list">${acs.age_bands
          .map((b) => `<li><span>${b.label}</span><span class="demo-legend-val">${b.pct}%</span></li>`)
          .join("")}</ul>
      </div>`;
    }

    let raceHtml = "";
    if (acs && acs.race_ethnicity && acs.race_ethnicity.length) {
      raceHtml = `<div class="demo-block">
        <h4 class="demo-block-title">Race & ethnicity</h4>
        <ul class="demo-legend-list">${acs.race_ethnicity
          .map((r) => `<li><span>${r.label}</span><span class="demo-legend-val">${r.pct}%</span></li>`)
          .join("")}</ul>
      </div>`;
    }

    let tenureHtml = "";
    if (acs && acs.housing_tenure) {
      const t = acs.housing_tenure;
      tenureHtml = `<div class="demo-block">
        <h4 class="demo-block-title">Housing tenure (occupied units)</h4>
        <div class="demo-tenure-row">
          <span>Owner ${t.owner_pct != null ? t.owner_pct + "%" : "—"}</span>
          <span>Renter ${t.renter_pct != null ? t.renter_pct + "%" : "—"}</span>
        </div>
      </div>`;
    }

    let regHtml = "";
    if (reg && reg.parties) {
      regHtml = `<div class="demo-block">
        <h4 class="demo-block-title">Registration mix</h4>
        ${AE.demography.registrationBarHtml(reg.parties)}
        <ul class="demo-legend-list">${reg.parties
          .map(
            (p) =>
              `<li><span>${p.label}</span><span class="demo-legend-val">${p.pct != null ? p.pct + "%" : "—"} · ${AE.demography.formatNumber(p.count)}</span></li>`
          )
          .join("")}</ul>
        <p class="demo-footnote">Registered voters on SOS Assembly worksheet — not CVAP or turnout.</p>
      </div>`;
    }

    const errNote =
      row.acs_error || acsIncomplete
        ? `<p class="demo-footnote warn">ACS section incomplete${row.acs_error ? `: ${row.acs_error}` : ""}.</p>`
        : "";

    return `<div class="demo-panel">
      <div class="demo-panel-head">
        <h3 class="card-title" style="margin:0">Counts & registration ${acsChip} ${regChip}</h3>
      </div>
      <p class="demo-source-line">${acsAsOf}<br />${regAsOf}</p>
      ${statsHtml}
      ${ageHtml}
      ${raceHtml}
      ${tenureHtml}
      ${regHtml}
      ${errNote}
      <p class="demo-footnote">Public aggregates only — not a voter file or field CRM. Refresh via <code>data/demography/README.md</code>.</p>
    </div>`;
  };
})();
