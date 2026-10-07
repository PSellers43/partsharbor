/* AssemblyEdge prototype — vanilla SPA navigation + interactions */

(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const state = {
    page: "portfolio",
    districtId: "ad-7",
    tab: "threat",
    theme: localStorage.getItem("ae-theme") || "dark",
    role: (window.AE && AE.CM && AE.CM.getRole()) || localStorage.getItem("ae-role") || "analyst",
    paletteIndex: 0,
    loading: false,
  };

  /* ——— Theme ——— */
  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme === "light" ? "light" : "dark");
    const btn = $("#theme-toggle");
    if (btn) btn.textContent = state.theme === "light" ? "Dark" : "Light";
  }

  function applyRole() {
    const role = state.role === "cm" ? "cm" : "analyst";
    state.role = role;
    document.body.dataset.role = role;
    if (AE.CM) AE.CM.setRole(role);
    $$(".role-btn").forEach((b) => b.classList.toggle("active", b.dataset.role === role));
    const sub = $(".brand-sub");
    if (sub) sub.textContent = role === "cm" ? "Campaign Manager" : "Threat Index";
  }

  /* ——— Routing ——— */
  function showPage(pageId) {
    state.page = pageId;
    $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + pageId));
    $$(".nav-link").forEach((n) => {
      n.classList.toggle("active", n.dataset.page === pageId);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function navigate(page, opts = {}) {
    if (opts.districtId) state.districtId = opts.districtId;
    if (opts.tab) state.tab = opts.tab;

    if (page === "district") {
      simulateLoad(() => {
        renderDistrict();
        showPage("district");
      });
    } else if (page === "brief") {
      renderBrief();
      showPage("brief");
    } else if (page === "methodology") {
      showPage("methodology");
    } else if (page === "cm") {
      renderCM();
      showPage("cm");
    } else if (page === "polling") {
      renderPollingPage();
      showPage("polling");
    } else if (page === "focus-map") {
      renderFocusMapPage();
      showPage("focus-map");
    } else {
      renderPortfolio();
      showPage("portfolio");
    }
  }

  function simulateLoad(done) {
    state.loading = true;
    const sk = $("#skeleton-wrap");
    const content = $("#district-content");
    if (sk && content) {
      sk.classList.add("show");
      content.hidden = true;
      showPage("district");
      setTimeout(() => {
        sk.classList.remove("show");
        content.hidden = false;
        state.loading = false;
        done();
      }, 420);
    } else {
      done();
    }
  }

  /* ——— Helpers ——— */
  function deltaClass(n) {
    if (n > 0) return "delta-up";
    if (n < 0) return "delta-down";
    return "delta-flat";
  }
  function deltaFmt(n, suffix) {
    const s = suffix || "";
    if (n > 0) return "+" + n + s;
    if (n < 0) return String(n) + s;
    return "0" + s;
  }
  function sparkline(series, cls) {
    const w = 72, h = 24, pad = 2;
    const min = Math.min(...series);
    const max = Math.max(...series);
    const range = max - min || 1;
    const pts = series
      .map((v, i) => {
        const x = pad + (i / (series.length - 1)) * (w - pad * 2);
        const y = h - pad - ((v - min) / range) * (h - pad * 2);
        return x.toFixed(1) + "," + y.toFixed(1);
      })
      .join(" ");
    return `<svg class="spark ${cls || ""}" width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts}"/></svg>`;
  }

  /* ——— Portfolio ——— */
  function renderPortfolio() {
    const grid = $("#district-grid");
    if (!grid) return;
    const elevated = AE.districts.filter((d) => d.status === "elevated").length;
    const watch = AE.districts.filter((d) => d.status === "watch").length;

    $("#stat-tracked").textContent = AE.districts.length;
    $("#stat-elevated").textContent = elevated;
    $("#stat-watch").textContent = watch;

    grid.innerHTML = AE.districts
      .map((d) => {
        const meta = AE.statusMeta[d.status];
        const barW = Math.min(100, d.threatIndex);
        return `
        <button type="button" class="district-card status-${d.status}" data-district="${d.id}" aria-label="Open ${d.code} ${d.name}">
          <div class="district-card-top">
            <div>
              <div class="district-code">${d.code}</div>
              <div class="district-name">${d.name} · ${d.region}</div>
            </div>
            <span class="chip ${meta.class}">${meta.label}</span>
          </div>
          <div class="threat-score">${d.threatIndex}<span class="unit">TI</span></div>
          <div class="threat-bar" aria-hidden="true"><span style="width:${barW}%"></span></div>
          <div class="district-card-meta">
            <span>24h <strong class="delta ${deltaClass(d.delta24h)}">${deltaFmt(d.delta24h)}</strong></span>
            <span>7d <strong class="delta ${deltaClass(d.delta7d)}">${deltaFmt(d.delta7d)}</strong></span>
            <span>${d.seatType}</span>
            <span class="chip chip-demo">Demo</span>
          </div>
        </button>`;
      })
      .join("");

    grid.querySelectorAll("[data-district]").forEach((btn) => {
      btn.addEventListener("click", () => navigate("district", { districtId: btn.dataset.district, tab: "threat" }));
    });

    renderPollingTeaser();
  }

  /* ——— Polling & gaps ——— */
  function pollRowHtml(row, compact) {
    const dMeta = AE.districts.find((x) => x.id === row.id);
    const poll = row.poll;
    const recent = poll && AE.polling.isRecent(poll);
    const hasPoll = !!poll;
    const gapMsg = (row.gap && row.gap.message) || "No public horse-race poll in the last 90 days";
    const isGapOnly = !hasPoll;
    const isStale = hasPoll && !recent;

    let bars = "";
    if (hasPoll && poll.margin) {
      const m = poll.margin;
      const u = m.undecided_pct || 0;
      const lead = m.leader_party === "R" ? "r" : "d";
      const trail = m.trailer_party === "R" ? "r" : "d";
      const leadPct = m.leader_pct || 0;
      const trailPct = m.trailer_pct || 0;
      bars = `
        <div class="poll-bar-labels">
          <span>${m.leader_name} (${m.leader_party}) ${leadPct}%</span>
          <span>${m.trailer_name} (${m.trailer_party}) ${trailPct}%</span>
          ${u ? `<span>Undecided ${u}%</span>` : ""}
        </div>
        <div class="poll-bar-track" aria-hidden="true">
          <span class="poll-bar-seg ${lead}" style="width:${leadPct}%"></span>
          <span class="poll-bar-seg ${trail}" style="width:${trailPct}%"></span>
          ${u ? `<span class="poll-bar-seg u" style="width:${u}%"></span>` : ""}
        </div>
        <div class="poll-meta-chips">
          <span class="chip ${recent ? "chip-poll-live" : "chip-poll-stale"}">${recent ? "Recent public poll" : "Latest available · stale"}</span>
          <span class="chip chip-demo">${poll.pollster}</span>
          ${poll.moe_pct != null ? `<span class="chip chip-demo">±${poll.moe_pct}% MoE</span>` : ""}
          <span class="chip chip-demo">n=${poll.sample_n || "—"} ${poll.population || ""}</span>
          <span class="chip chip-demo">Field ${poll.field_start || "—"} → ${poll.field_end || "—"}</span>
          ${poll.sponsor ? `<span class="chip chip-demo" title="Sponsor">${poll.sponsor}</span>` : ""}
        </div>
        ${poll.source_url ? `<a class="poll-source-link" href="${poll.source_url}" target="_blank" rel="noopener noreferrer">${poll.source_label || "Source"} ↗</a>` : ""}`;
    } else {
      bars = `<div class="poll-gap-block"><div class="poll-gap-message">${gapMsg}</div></div>`;
    }

    const gapChip =
      isGapOnly || isStale
        ? `<span class="chip chip-gap">${gapMsg}</span>`
        : "";

    const actions = compact
      ? ""
      : `<div class="poll-row-actions">
          ${gapChip}
          <button type="button" class="btn" data-district-open="${row.id}">District detail</button>
        </div>`;

    return `
      <article class="poll-row ${isGapOnly || isStale ? "is-gap" : ""}" role="listitem">
        <div class="poll-row-head">
          <div class="poll-code">${row.code}</div>
          <div class="poll-race">${row.race_label || (dMeta ? dMeta.name + " · " + dMeta.region : "")}</div>
          ${dMeta ? `<div class="poll-meta-chips" style="margin-top:8px"><span class="chip chip-demo">TI ${dMeta.threatIndex} (illustrative)</span></div>` : ""}
        </div>
        <div class="poll-bars">${bars}</div>
        ${actions}
      </article>`;
  }

  function renderPollingPage() {
    const root = AE.pollingData;
    const el = $("#polling-infographic");
    const badge = $("#polling-data-badge");
    const note = $("#polling-meta-note");
    if (!el) return;

    if (AE.pollingLoadError || !root) {
      if (badge) {
        badge.textContent = "DATA MISSING";
        badge.className = "chip chip-gap";
      }
      el.innerHTML = `<div class="empty-state"><h3>Polling JSON not loaded</h3><p>${AE.pollingLoadError || "Fetch failed"} — add <code>data/polling/latest.json</code>.</p></div>`;
      return;
    }

    if (badge) {
      badge.textContent = "CURATED PUBLIC POLLS";
      badge.className = "chip chip-live";
    }
    if (note) {
      const asOf = root.updated_at ? formatAsOf(root.updated_at) : "—";
      note.innerHTML = `As of <strong>${asOf}</strong> · Gap threshold <strong>${root.gap_recent_days || 90} days</strong> · ${root.notes || ""}`;
    }

    const rows = (root.districts || []).slice().sort((a, b) => a.code.localeCompare(b.code));
    el.innerHTML = rows.map((r) => pollRowHtml(r, false)).join("");
    el.querySelectorAll("[data-district-open]").forEach((btn) => {
      btn.addEventListener("click", () => navigate("district", { districtId: btn.dataset.districtOpen, tab: "threat" }));
    });
  }

  function renderPollingTeaser() {
    const body = $("#polling-teaser-body");
    const badge = $("#polling-teaser-badge");
    if (!body) return;
    const root = AE.pollingData;
    if (!root || !root.districts) {
      body.textContent = AE.pollingLoadError ? "Polling data unavailable." : "Loading…";
      if (badge) badge.textContent = "—";
      return;
    }
    const gaps = root.districts.filter((row) => {
      if (!row.poll) return true;
      return !AE.polling.isRecent(row.poll);
    });
    if (badge) badge.textContent = gaps.length + " gap" + (gaps.length === 1 ? "" : "s");
    body.innerHTML = `<div class="intel-gap-pills">${gaps
      .map((g) => `<span class="intel-gap-pill">${g.code}</span>`)
      .join("")}</div><p style="margin:8px 0 0">${gaps.length}/${root.districts.length} districts without a recent public poll.</p>`;
  }

  function renderDistrictPollingStrip(d) {
    const el = $("#district-polling-strip");
    if (!el) return;
    const row = AE.polling && AE.polling.districtRow(d.id);
    if (!row) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = `<div class="card" style="padding:12px 14px"><h3 class="card-title" style="margin-bottom:8px">Polling & gaps</h3>${pollRowHtml(row, true)}</div>`;
  }

  /* ——— Focus map ——— */
  function renderFocusMapPage() {
    const wrap = $("#focus-map-wrap");
    const legend = $("#focus-legend");
    const rank = $("#focus-rank-list");
    if (!wrap) return;

    if (AE.mapGeoLoadError || !AE.mapGeo) {
      wrap.innerHTML = `<div class="empty-state"><h3>Map geometry missing</h3><p>${AE.mapGeoLoadError || ""}</p></div>`;
      return;
    }

    const w = 400;
    const h = 480;
    const layers = AE.focusMap.featurePaths(w, h);
    const contextShapes = layers.context
      .map(
        (f) =>
          `<path class="district-context" aria-hidden="true" data-context-ad="${f.code}" d="${f.d}"></path>`
      )
      .join("");
    const beachShapes = layers.beachhead
      .map(
        (f) =>
          `<path class="district-shape ${f.band.class}" tabindex="0" role="link" aria-label="${f.code} focus score ${f.score}" data-district="${f.id}" d="${f.d}"></path>`
      )
      .join("");

    const attr = AE.focusMap.attributionHtml();
    wrap.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" class="focus-map-svg" aria-label="California Assembly focus map, CRC 2020 boundaries">
        <g class="map-context-layer">${contextShapes}</g>
        <g class="map-beachhead-layer">${beachShapes}</g>
      </svg>
      <p class="focus-map-attribution">${attr}</p>`;

    wrap.querySelectorAll("[data-district]").forEach((path) => {
      const go = () => navigate("district", { districtId: path.dataset.district, tab: "threat" });
      path.addEventListener("click", go);
      path.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          go();
        }
      });
    });

    if (legend) {
      legend.innerHTML = `
        <span class="focus-legend-item"><span class="focus-legend-swatch" style="background:#b8860b"></span> High focus (70+)</span>
        <span class="focus-legend-item"><span class="focus-legend-swatch" style="background:#8b6914"></span> Elevated (50–69)</span>
        <span class="focus-legend-item"><span class="focus-legend-swatch" style="background:#5c4a12"></span> Watch (&lt;50)</span>
        <span class="focus-legend-item"><span class="chip chip-demo">Threat Index illustrative</span></span>
        <span class="focus-legend-item">Gray outlines = other ADs (context)</span>`;
    }

    if (rank) {
      const sorted = AE.districts
        .map((d) => ({ d, ...AE.focusMap.computeScore(d.id) }))
        .sort((a, b) => b.score - a.score);
      rank.innerHTML = sorted
        .map(({ d, score, parts }) => {
          const band = AE.focusMap.scoreBand(score);
          return `<div class="focus-rank-item">
            <button type="button" data-district-open="${d.id}">${d.code}</button>
            <span class="chip ${band.class === "focus-high" ? "chip-gap" : "chip-demo"}">${score} · ${band.label}</span>
            <span style="font-size:10px;color:var(--text-dim)">TI ${parts.threatIndex}</span>
          </div>`;
        })
        .join("");
      rank.querySelectorAll("[data-district-open]").forEach((btn) => {
        btn.addEventListener("click", () => navigate("district", { districtId: btn.dataset.districtOpen, tab: "threat" }));
      });
    }
  }

  /* ——— District detail ——— */
  function renderDistrict() {
    const d = AE.districts.find((x) => x.id === state.districtId) || AE.districts[0];
    state.districtId = d.id;
    const meta = AE.statusMeta[d.status];

    $("#detail-code").textContent = d.code;
    $("#detail-name").textContent = d.name;
    $("#detail-region").textContent = d.region + " · " + d.lean;
    $("#detail-incumbent").textContent = d.incumbent + (d.party !== "—" ? ` (${d.party})` : "");
    $("#detail-ti").textContent = d.threatIndex;
    $("#detail-status").className = "chip " + meta.class;
    $("#detail-status").textContent = meta.label;
    $("#detail-d24").textContent = deltaFmt(d.delta24h);
    $("#detail-d24").className = "delta " + deltaClass(d.delta24h);
    $("#detail-d7").textContent = deltaFmt(d.delta7d);
    $("#detail-d7").className = "delta " + deltaClass(d.delta7d);

    // Deep demo only fully wired for AD-7; others show empty/partial
    const isDeep = d.id === "ad-7";
    $("#deep-demo-note").hidden = isDeep;
    $("#deep-demo-note").textContent = isDeep
      ? ""
      : `${d.code} shows portfolio Threat Index. Full factor / money / ads / narrative panels are wired for AD-7 (Hoover) as the deep demo — open AD-7 for the complete desk.`;

    renderDistrictPollingStrip(d);
    renderThreat(d);
    renderMoney(d);
    renderAds(d);
    renderNarrative(d);
    renderRival(d);
    renderAlerts(d);
    setTab(state.tab || "threat");
  }

  function renderThreat(d) {
    const el = $("#threat-panel");
    const factors = AE.factors[d.id];
    if (!factors) {
      el.innerHTML = `<div class="empty-state"><h3>Factors available in AD-7 deep demo</h3><p>Portfolio score is live above. Click AD-7 from home for explainable factor breakdown.</p>
        <button type="button" class="btn btn-primary" id="goto-ad7">Open AD-7</button></div>`;
      $("#goto-ad7")?.addEventListener("click", () => navigate("district", { districtId: "ad-7", tab: "threat" }));
      return;
    }
    el.innerHTML = `
      <div class="panel-grid">
        <div class="card">
          <h3 class="card-title">Threat Index breakdown <span class="chip chip-demo">Demo</span></h3>
          <p style="margin:0 0 12px;font-size:12.5px;color:var(--text-muted)">Weighted composite. Click a factor for methodology.</p>
          <div class="factor-list">
            ${factors
              .map(
                (f) => `
              <button type="button" class="factor-row" data-factor="${f.id}">
                <div>
                  <div class="factor-label">${f.label}
                    <span class="delta ${f.trend === "up" ? "delta-up" : f.trend === "down" ? "delta-down" : "delta-flat"}" style="margin-left:6px;font-size:11px">${f.trend === "up" ? "↑" : f.trend === "down" ? "↓" : "→"}</span>
                  </div>
                  <div class="factor-blurb">${f.blurb}</div>
                </div>
                <div>
                  <div class="factor-score">${f.score}</div>
                  <div class="factor-weight">w ${(f.weight * 100).toFixed(0)}%</div>
                </div>
                <div class="factor-meter"><i style="width:${f.score}%"></i></div>
              </button>`
              )
              .join("")}
          </div>
        </div>
        <div class="card">
          <h3 class="card-title">How to read</h3>
          <p style="margin:0;font-size:13px;color:var(--text-muted);line-height:1.55">
            Threat Index is a <strong style="color:var(--text)">relative desk signal</strong>, not a prediction of seat outcome.
            Elevated (≥65 demo threshold) means money, IE, ads, narrative, or poll factors moved enough to warrant operator attention this week.
          </p>
          <ul style="margin:14px 0 0;padding-left:18px;color:var(--text-muted);font-size:13px;line-height:1.55">
            <li>Scores are illustrative placeholders with plausible structure.</li>
            <li>Production wires CAL-ACCESS, ad libraries, and sourced headlines only.</li>
            <li>Decision chips on Alerts are guidance types — not automated orders.</li>
          </ul>
          <button type="button" class="btn" style="margin-top:16px" data-page-jump="methodology">Methodology & trust</button>
        </div>
      </div>`;
    el.querySelectorAll("[data-factor]").forEach((btn) => {
      btn.addEventListener("click", () => openDrawer(btn.dataset.factor));
    });
    el.querySelector("[data-page-jump]")?.addEventListener("click", () => navigate("methodology"));
  }

  function formatAsOf(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleString("en-US", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }) + " PT";
    } catch {
      return iso;
    }
  }

  function formatMoneyExact(n) {
    if (n == null || Number.isNaN(n)) return "—";
    if (Math.abs(n) >= 1000) return "$" + Math.round(n).toLocaleString("en-US");
    return "$" + Number(n).toFixed(0);
  }

  function liveDistrictMoney(districtId) {
    const live = AE.liveMoney;
    if (!live || !live.districts) return null;
    return live.districts[districtId] || null;
  }

  function renderMoney(d) {
    const el = $("#money-panel");
    const liveDist = liveDistrictMoney(d.id);
    const useLive = liveDist && liveDist.live && Array.isArray(liveDist.candidates) && liveDist.candidates.some((c) => c.live);
    const weakLive = liveDist && !useLive && liveDist.status === "weak";

    if (useLive || weakLive) {
      const asOf = formatAsOf((AE.liveMoney && (AE.liveMoney.data_as_of || AE.liveMoney.generated_at)) || "");
      const badge = useLive
        ? `<span class="chip chip-live">LIVE CAL-ACCESS</span>`
        : `<span class="chip chip-live-weak">CAL-ACCESS · weak match</span>`;
      const rows = (list) =>
        list
          .map((r) => {
            const spendDelta = r.deltaSpend;
            const deltaCell =
              spendDelta == null
                ? `<span class="delta delta-flat" title="WoW not computable from Form 460 period summaries">n/a</span>`
                : `<span class="delta ${deltaClass(spendDelta)}">${deltaFmt(spendDelta, "%")} WoW</span>`;
            const q = r.match_quality ? ` · ${r.match_quality}` : "";
            const role = r.role || (r.side === "oppose" ? "IE oppose" : r.side === "support" ? "IE support" : "");
            const tag = r.live === false
              ? `<span class="chip chip-demo">Unmatched</span>`
              : `<span class="chip chip-live">Filed</span>`;
            const series = Array.isArray(r.series) && r.series.length ? r.series : [0, 0, 0, 0, 0, 0, 0, 0];
            const sparkCls = r.side === "oppose" ? "oppose" : r.side === "support" ? "support" : "";
            const sub = r.committee_name
              ? `<div class="money-role">${role}${q}</div><div class="money-role" style="opacity:0.8">${r.committee_name}</div>`
              : `<div class="money-role">${role}${q}</div>`;
            return `<tr>
              <td><div class="money-name">${r.name}</div>${sub}</td>
              <td class="mono">${formatMoneyExact(r.receipts)} ${tag}</td>
              <td class="mono">${formatMoneyExact(r.spend)}</td>
              <td>${deltaCell}</td>
              <td>${sparkline(series, sparkCls)}</td>
            </tr>`;
          })
          .join("");

      const src = (AE.liveMoney && AE.liveMoney.source) || {};
      el.innerHTML = `
        <div class="card">
          <h3 class="card-title">Candidate &amp; IE money ${badge}</h3>
          <p class="money-source-note">
            As of <strong>${asOf || "—"}</strong>
            · Official SOS daily ZIP
            ${src.url ? `· <a href="${src.url}" target="_blank" rel="noopener noreferrer">dbwebexport.zip</a>` : ""}
            · Public CAL-ACCESS (not FPPC endorsement)
            ${weakLive ? " · <strong>Match weak — treat figures cautiously</strong>" : ""}
          </p>
          <table class="money-table">
            <thead><tr><th>Entity</th><th>Receipts</th><th>Spend</th><th>Spend Δ</th><th>8w pace</th></tr></thead>
            <tbody>
              ${rows(liveDist.candidates || [])}
              ${rows(liveDist.ie || [])}
            </tbody>
          </table>
          <p class="money-source-note" style="margin-top:12px">
            Provenance: Form 460 SMRY lines 5/11 (committee cycle period sums) + Form 496/S496 IE amounts.
            Candidate WoW is n/a from period summaries; IE WoW uses expenditure dates when present.
            Name↔district matching is imperfect — see <code>CALACCESS.md</code>.
          </p>
        </div>`;
      return;
    }

    // Fallback: demo data — never silently mixed with live
    const data = AE.money[d.id];
    if (!data) {
      el.innerHTML = `<div class="empty-state"><h3>Money panel — AD-7 deep demo</h3><p>Illustrative receipts/spend with WoW deltas and sparklines. Run <code>scripts/update-calaccess.sh</code> for LIVE CAL-ACCESS.</p></div>`;
      return;
    }
    const rows = (list, sparkCls) =>
      list
        .map((r) => {
          const spendDelta = r.deltaSpend;
          return `<tr>
            <td><div class="money-name">${r.name}</div><div class="money-role">${r.role || (r.side === "oppose" ? "IE oppose" : "IE support")}</div></td>
            <td class="mono">${AE.formatMoney(r.receipts)} <span class="chip chip-demo">Demo</span></td>
            <td class="mono">${AE.formatMoney(r.spend)}</td>
            <td class="delta ${deltaClass(spendDelta)}">${deltaFmt(spendDelta, "%")} WoW</td>
            <td>${sparkline(r.series, sparkCls || (r.side === "oppose" ? "oppose" : r.side === "support" ? "support" : ""))}</td>
          </tr>`;
        })
        .join("");

    const missingNote = AE.liveMoneyLoadError
      ? `Live JSON missing or failed (${AE.liveMoneyLoadError}). Showing demo.`
      : "Live CAL-ACCESS JSON not loaded — showing demo placeholders.";

    el.innerHTML = `
      <div class="card">
        <h3 class="card-title">Candidate & IE money <span class="chip chip-demo">DEMO / ILLUSTRATIVE</span></h3>
        <p class="money-source-note">${missingNote} ${data.updated} · Not real CAL-ACCESS totals</p>
        <table class="money-table">
          <thead><tr><th>Entity</th><th>Receipts</th><th>Spend</th><th>Spend Δ</th><th>8w pace</th></tr></thead>
          <tbody>
            ${rows(data.candidates)}
            ${rows(data.ie)}
          </tbody>
        </table>
      </div>`;
  }

  function loadLiveMoney() {
    AE.liveMoney = null;
    AE.liveMoneyLoadError = null;
    const url = "data/calaccess/latest/money-by-district.json";
    return fetch(url, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.liveMoney = json;
        AE.liveMoneyLoadError = null;
        // Refresh money panel if currently viewing a district
        if (state.page === "district") {
          const d = AE.districts.find((x) => x.id === state.districtId);
          if (d) renderMoney(d);
        }
        if (state.page === "focus-map") renderFocusMapPage();
        if (state.page === "portfolio") renderPortfolio();
      })
      .catch((err) => {
        AE.liveMoney = null;
        AE.liveMoneyLoadError = String(err && err.message ? err.message : err);
      });
  }

  function refreshPollingViews() {
    if (state.page === "polling") renderPollingPage();
    if (state.page === "portfolio") renderPollingTeaser();
    if (state.page === "district") {
      const d = AE.districts.find((x) => x.id === state.districtId);
      if (d) renderDistrictPollingStrip(d);
    }
    if (state.page === "focus-map") renderFocusMapPage();
  }

  function renderAds(d) {
    const el = $("#ads-panel");
    const ads = AE.ads[d.id];
    if (!ads) {
      el.innerHTML = `<div class="empty-state"><h3>Ads panel — AD-7 deep demo</h3><p>Meta + Google transparency-style cards.</p></div>`;
      return;
    }
    el.innerHTML = `
      <div class="ads-grid">
        ${ads
          .map(
            (a) => `
          <div class="ad-card">
            <div class="ad-platform">${a.platform} <span class="chip chip-demo">${a.note}</span></div>
            <div class="ad-sponsor">${a.sponsor}</div>
            <dl class="ad-stats">
              <div><dt>Creatives</dt><dd>${a.creatives}</dd></div>
              <div><dt>Spend band</dt><dd>${a.spendBand}</dd></div>
              <div><dt>First seen</dt><dd>${a.firstSeen}</dd></div>
              <div><dt>Last seen</dt><dd>${a.lastSeen}</dd></div>
            </dl>
            <a class="ad-link" href="${a.link}" target="_blank" rel="noopener noreferrer">Open ${a.platform === "Meta" ? "Ad Library" : "Ads Transparency"} ↗</a>
          </div>`
          )
          .join("")}
      </div>`;
  }

  function renderNarrative(d) {
    const el = $("#narrative-panel");
    const items = AE.narrative[d.id];
    if (!items) {
      el.innerHTML = `<div class="empty-state"><h3>Narrative feed — AD-7 deep demo</h3></div>`;
      return;
    }
    el.innerHTML = `
      <div class="card">
        <h3 class="card-title">Sourced headlines <span class="chip chip-demo">Demo feed</span></h3>
        <div class="feed-list">
          ${items
            .map(
              (n) => `
            <article class="feed-item">
              <div>
                <div class="feed-outlet">${n.outlet}</div>
                <div class="feed-title">${n.title}</div>
                <div class="feed-ts">${n.ts}</div>
              </div>
              <span class="chip chip-sentiment-${n.sentiment}">${n.sentiment}</span>
            </article>`
            )
            .join("")}
        </div>
      </div>`;
  }

  function renderRival(d) {
    const el = $("#rival-panel");
    const r = AE.rival[d.id];
    if (!r) {
      el.innerHTML = `<div class="empty-state"><h3>Rival card — AD-7 deep demo</h3></div>`;
      return;
    }
    el.innerHTML = `
      <div class="panel-grid">
        <div class="card rival-block">
          <h3 class="card-title">Opponent</h3>
          <h3>${r.opponent} <span class="chip chip-watch">${r.party}</span></h3>
          <p>${r.notes}</p>
          <h3 class="card-title">IE supporting challenger / oppose R</h3>
          <ul class="ie-list">
            ${r.ieSupporters
              .map(
                (i) => `<li><div><div class="ie-name">${i.name}</div><div class="ie-role">${i.role}</div></div><span class="ie-band">${i.spendBand}</span></li>`
              )
              .join("")}
          </ul>
        </div>
        <div class="card rival-block">
          <h3 class="card-title">IE allies (support incumbent)</h3>
          <ul class="ie-list">
            ${r.ieAllies
              .map(
                (i) => `<li><div><div class="ie-name">${i.name}</div><div class="ie-role">${i.role}</div></div><span class="ie-band">${i.spendBand}</span></li>`
              )
              .join("")}
          </ul>
          <p style="margin-top:16px;font-size:12px;color:var(--text-dim)">All spend bands labeled demo. Production maps to filed IE disclosures only.</p>
        </div>
      </div>`;
  }

  function renderAlerts(d) {
    const el = $("#alerts-panel");
    const items = AE.alerts[d.id];
    if (!items) {
      el.innerHTML = `<div class="empty-state"><h3>Alerts — AD-7 deep demo</h3></div>`;
      return;
    }
    el.innerHTML = `
      <div class="card">
        <h3 class="card-title">What changed <span class="chip chip-demo">Guidance chips ≠ certainty</span></h3>
        <div class="timeline">
          ${items
            .map(
              (a) => `
            <div class="timeline-item">
              <div class="timeline-ts">${a.ts}</div>
              <div class="timeline-title">${a.title}</div>
              <div class="timeline-detail">${a.detail}</div>
              <span class="chip chip-decision-${a.decision}">${a.decisionLabel}</span>
            </div>`
            )
            .join("")}
        </div>
      </div>`;
  }

  function setTab(tabId) {
    state.tab = tabId;
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabId));
    $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tabId));
  }

  /* ——— Brief ——— */
  function renderBrief() {
    const d = AE.districts.find((x) => x.id === "ad-7");
    const b = AE.brief["ad-7"];
    const el = $("#brief-body");
    el.innerHTML = `
      <div class="brief-shell">
        <div class="brief-masthead">
          <div class="brief-masthead-main">
            <div class="brief-product">AssemblyEdge · Monday Brief</div>
            <div class="brief-week">${b.weekOf} · ${d.code} ${d.name}</div>
          </div>
          <div class="brief-masthead-aside">
            <span class="chip chip-elevated">Elevated</span>
            <div class="brief-ti">${d.threatIndex} <span class="brief-ti-unit">TI</span></div>
            <div class="brief-ti-delta">7d <span class="delta delta-up">${deltaFmt(d.delta7d)}</span></div>
          </div>
        </div>
        <p class="chip chip-demo brief-demo-chip">DEMO / ILLUSTRATIVE — Not filed campaign data</p>
        <h2 class="brief-headline">${b.headline}</h2>
        <ul class="brief-bullets">
          ${b.bullets.map((x) => `<li>${x}</li>`).join("")}
        </ul>
        <h3 class="card-title">Recommended decision types</h3>
        <div class="brief-decisions">
          ${b.decisions
            .map(
              (dec) => `
            <div class="brief-decision">
              <span class="chip chip-decision-${dec.type}">${dec.label}</span>
              <span class="note">${dec.note}</span>
            </div>`
            )
            .join("")}
        </div>
        <div class="brief-footer">
          AssemblyEdge prototype · Sources in production: CAL-ACCESS, Meta Ad Library, Google Ads Transparency, sourced news.
          Not an official FPPC, Secretary of State, or caucus product. Decision chips are guidance taxonomy only.
        </div>
      </div>`;
  }


  /* ——— Campaign Manager ——— */
  function renderCM() {
    const d = AE.districts.find((x) => x.id === "ad-7");
    const ti = $("#cm-ti-value");
    if (ti && d) {
      ti.textContent = d.threatIndex;
      ti.style.color = "var(--danger)";
    }
    const mode = AE.CM.getRaceMode();
    $$(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    const modeMeta = AE.cmMode[mode];
    const blurb = $("#cm-mode-blurb");
    if (blurb && modeMeta) {
      blurb.innerHTML = `<strong>${modeMeta.label}</strong> — ${modeMeta.blurb} <span class="chip chip-demo">Demo mode switch</span>`;
    }

    const list = $("#cm-priority-list");
    if (list) {
      const sorted = [...AE.cmPriorities].sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 };
        return order[a.urgency] - order[b.urgency];
      });
      list.innerHTML = sorted
        .map((p) => {
          const acts = p.actions
            .map((a) => {
              const m = AE.cmActionMeta[a];
              return `<span class="chip ${m.class}">${m.label}</span>`;
            })
            .join(" ");
          return `<article class="cm-priority ${AE.CM.urgencyClass(p.urgency)}" data-priority="${p.id}">
            <div class="cm-priority-top">
              <span class="cm-horizon">${p.horizon}</span>
              <span class="cm-urgency-label">${p.urgency}</span>
            </div>
            <h4 class="cm-priority-title">${p.title}</h4>
            <p class="cm-priority-detail">${p.detail}</p>
            <div class="cm-priority-tags">${acts} ${AE.CM.evidenceChips(p.evidence)}</div>
            <div class="cm-priority-actions no-print">
              ${AE.cmDecisionTypes
                .map(
                  (dt) =>
                    `<button type="button" class="btn cm-quick-log" data-priority="${p.id}" data-decision="${dt.id}">${dt.label}</button>`
                )
                .join("")}
            </div>
          </article>`;
        })
        .join("");
      list.querySelectorAll(".cm-quick-log").forEach((btn) => {
        btn.addEventListener("click", () => {
          quickLog(btn.dataset.priority, btn.dataset.decision);
        });
      });
    }

    // Form selects
    const selP = $("#cm-log-priority");
    const selD = $("#cm-log-decision");
    if (selP) {
      selP.innerHTML = AE.cmPriorities.map((p) => `<option value="${p.id}">${p.horizon} · ${p.title}</option>`).join("");
    }
    if (selD) {
      selD.innerHTML = AE.cmDecisionTypes.map((d) => `<option value="${d.id}">${d.label}</option>`).join("");
    }

    renderCMLog();
    renderChecklist();
    renderDoctrineSidebar();
  }

  function quickLog(priorityId, decisionId) {
    const p = AE.cmPriorities.find((x) => x.id === priorityId);
    const dt = AE.cmDecisionTypes.find((x) => x.id === decisionId);
    AE.CM.addLogEntry({
      id: "log-" + Date.now(),
      ts: new Date().toISOString(),
      priorityId,
      priorityTitle: p ? p.title : priorityId,
      decision: decisionId,
      decisionLabel: dt ? dt.label : decisionId,
      note: "Quick mark from board",
      district: "AD-7",
    });
    renderCMLog();
  }

  function renderCMLog() {
    const el = $("#cm-log-list");
    if (!el) return;
    const log = AE.CM.getLog();
    if (!log.length) {
      el.innerHTML = `<div class="empty-state" style="padding:24px"><h3>No decisions logged yet</h3><p>Use quick buttons on a priority or the form above.</p></div>`;
      return;
    }
    el.innerHTML = log
      .map((e) => {
        const when = formatLocal(e.ts);
        return `<div class="cm-log-item">
          <div class="cm-log-meta"><span class="chip chip-decision-${e.decision}">${e.decisionLabel}</span>
            <span class="feed-ts">${when}</span></div>
          <div class="cm-log-title">${AE.CM.escapeHtml(e.priorityTitle)}</div>
          <div class="cm-log-note">${AE.CM.escapeHtml(e.note || "")}</div>
        </div>`;
      })
      .join("");
  }

  function formatLocal(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleString("en-US", { timeZone: "America/Los_Angeles", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PT";
    } catch {
      return iso;
    }
  }

  function renderChecklist() {
    const el = $("#cm-checklist");
    const dateEl = $("#cm-check-date");
    if (!el) return;
    const { key, map } = AE.CM.getChecklist();
    if (dateEl) dateEl.textContent = key;
    const groups = {};
    AE.cmChecklist.forEach((c) => {
      if (!groups[c.group]) groups[c.group] = [];
      groups[c.group].push(c);
    });
    el.innerHTML = Object.keys(groups)
      .map((g) => {
        const items = groups[g]
          .map((c) => {
            const checked = !!map[c.id];
            return `<label class="cm-check-item ${checked ? "done" : ""}">
              <input type="checkbox" data-check="${c.id}" ${checked ? "checked" : ""} />
              <span>${c.label}</span>
            </label>`;
          })
          .join("");
        return `<div class="cm-check-group"><div class="cm-check-group-title">${g}</div>${items}</div>`;
      })
      .join("");
    el.querySelectorAll("[data-check]").forEach((input) => {
      input.addEventListener("change", () => {
        AE.CM.toggleCheck(input.dataset.check);
        renderChecklist();
      });
    });
  }

  function renderDoctrineSidebar() {
    const el = $("#cm-doctrine-list");
    if (!el) return;
    el.innerHTML = AE.doctrine
      .map((d) => `<li><strong>${d.cite}</strong><br/><span>${d.principle}</span></li>`)
      .join("");
  }

  /* ——— Drawer ——— */
  function openDrawer(factorId) {
    const m = AE.methodology[factorId];
    if (!m) return;
    $("#drawer-title").textContent = m.title;
    $("#drawer-body").textContent = m.body;
    $("#drawer").classList.add("open");
    $("#drawer-overlay").classList.add("open");
    $("#drawer-close").focus();
  }
  function closeDrawer() {
    $("#drawer").classList.remove("open");
    $("#drawer-overlay").classList.remove("open");
  }

  /* ——— Command palette ——— */
  function paletteItems() {
    const districts = AE.districts.map((d) => ({
      id: "d-" + d.id,
      label: `${d.code} · ${d.name}`,
      hint: "District",
      run: () => navigate("district", { districtId: d.id, tab: "threat" }),
    }));
    const actions = [
      { id: "home", label: "Portfolio home", hint: "Go", run: () => navigate("portfolio") },
      { id: "polling", label: "Polling & gaps", hint: "Go", run: () => navigate("polling") },
      { id: "focus", label: "Focus map", hint: "Go", run: () => navigate("focus-map") },
      { id: "cm", label: "CM Board · Today’s priorities", hint: "Go", run: () => navigate("cm") },
      { id: "brief", label: "Monday Brief · AD-7", hint: "Go", run: () => navigate("brief") },
      { id: "method", label: "Methodology / Trust", hint: "Go", run: () => navigate("methodology") },
      {
        id: "role-cm",
        label: "Switch role → Campaign Manager",
        hint: "Role",
        run: () => {
          state.role = "cm";
          applyRole();
          navigate("cm");
        },
      },
      {
        id: "role-analyst",
        label: "Switch role → Analyst",
        hint: "Role",
        run: () => {
          state.role = "analyst";
          applyRole();
          navigate("portfolio");
        },
      },
      { id: "tab-threat", label: "AD-7 · Threat Index", hint: "Tab", run: () => navigate("district", { districtId: "ad-7", tab: "threat" }) },
      { id: "tab-money", label: "AD-7 · Money", hint: "Tab", run: () => navigate("district", { districtId: "ad-7", tab: "money" }) },
      { id: "tab-ads", label: "AD-7 · Ads", hint: "Tab", run: () => navigate("district", { districtId: "ad-7", tab: "ads" }) },
      { id: "tab-narrative", label: "AD-7 · Narrative", hint: "Tab", run: () => navigate("district", { districtId: "ad-7", tab: "narrative" }) },
      { id: "tab-alerts", label: "AD-7 · Alerts", hint: "Tab", run: () => navigate("district", { districtId: "ad-7", tab: "alerts" }) },
      {
        id: "theme",
        label: state.theme === "light" ? "Switch to dark theme" : "Switch to light theme",
        hint: "Theme",
        run: () => {
          state.theme = state.theme === "light" ? "dark" : "light";
          localStorage.setItem("ae-theme", state.theme);
          applyTheme();
        },
      },
    ];
    return [...actions, ...districts];
  }

  function openPalette() {
    const overlay = $("#palette-overlay");
    const input = $("#palette-input");
    overlay.classList.add("open");
    input.value = "";
    state.paletteIndex = 0;
    renderPaletteList("");
    setTimeout(() => input.focus(), 10);
  }
  function closePalette() {
    $("#palette-overlay").classList.remove("open");
  }
  function renderPaletteList(q) {
    const list = $("#palette-list");
    const items = paletteItems().filter((i) => i.label.toLowerCase().includes((q || "").toLowerCase()));
    if (!items.length) {
      list.innerHTML = `<div class="palette-empty">No matches</div>`;
      return;
    }
    if (state.paletteIndex >= items.length) state.paletteIndex = 0;
    list.innerHTML = items
      .map(
        (i, idx) =>
          `<button type="button" class="palette-item ${idx === state.paletteIndex ? "active" : ""}" data-idx="${idx}">
            <span>${i.label}</span><span class="hint">${i.hint}</span>
          </button>`
      )
      .join("");
    list._items = items;
    list.querySelectorAll(".palette-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = items[+btn.dataset.idx];
        closePalette();
        item.run();
      });
    });
  }
  function paletteMove(dir) {
    const list = $("#palette-list");
    const items = list._items || [];
    if (!items.length) return;
    state.paletteIndex = (state.paletteIndex + dir + items.length) % items.length;
    renderPaletteList($("#palette-input").value);
  }
  function paletteConfirm() {
    const items = $("#palette-list")._items || [];
    const item = items[state.paletteIndex];
    if (item) {
      closePalette();
      item.run();
    }
  }

  /* ——— Init ——— */
  function bind() {
    $$(".nav-link").forEach((n) => {
      n.addEventListener("click", () => navigate(n.dataset.page));
    });
    $$("[data-page-jump]").forEach((n) => {
      n.addEventListener("click", () => navigate(n.dataset.pageJump));
    });
    $(".brand")?.addEventListener("click", () => navigate(state.role === "cm" ? "cm" : "portfolio"));
    $$(".role-btn").forEach((b) => {
      b.addEventListener("click", () => {
        state.role = b.dataset.role;
        applyRole();
        if (state.role === "cm") navigate("cm");
        else navigate("portfolio");
      });
    });
    $$(".mode-btn").forEach((b) => {
      b.addEventListener("click", () => {
        AE.CM.setRaceMode(b.dataset.mode);
        renderCM();
      });
    });
    $("#cm-decision-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const priorityId = $("#cm-log-priority").value;
      const decisionId = $("#cm-log-decision").value;
      const note = ($("#cm-log-note").value || "").trim() || "Logged from form";
      const p = AE.cmPriorities.find((x) => x.id === priorityId);
      const dt = AE.cmDecisionTypes.find((x) => x.id === decisionId);
      AE.CM.addLogEntry({
        id: "log-" + Date.now(),
        ts: new Date().toISOString(),
        priorityId,
        priorityTitle: p ? p.title : priorityId,
        decision: decisionId,
        decisionLabel: dt ? dt.label : decisionId,
        note,
        district: "AD-7",
      });
      $("#cm-log-note").value = "";
      renderCMLog();
    });
    $("#cm-log-clear")?.addEventListener("click", () => {
      AE.CM.clearLog();
      renderCMLog();
    });
    $("#theme-toggle")?.addEventListener("click", () => {
      state.theme = state.theme === "light" ? "dark" : "light";
      localStorage.setItem("ae-theme", state.theme);
      applyTheme();
    });
    $("#cmd-open")?.addEventListener("click", openPalette);
    $("#export-pdf")?.addEventListener("click", () => window.print());
    $("#open-brief-from-detail")?.addEventListener("click", () => navigate("brief"));
    $("#goto-cm-board")?.addEventListener("click", () => navigate("cm"));

    $$(".tab").forEach((t) => {
      t.addEventListener("click", () => setTab(t.dataset.tab));
    });
    $("#back-portfolio")?.addEventListener("click", () => navigate("portfolio"));

    $("#drawer-overlay")?.addEventListener("click", closeDrawer);
    $("#drawer-close")?.addEventListener("click", closeDrawer);
    $("#palette-overlay")?.addEventListener("click", (e) => {
      if (e.target.id === "palette-overlay") closePalette();
    });
    $("#palette-input")?.addEventListener("input", (e) => {
      state.paletteIndex = 0;
      renderPaletteList(e.target.value);
    });

    document.addEventListener("keydown", (e) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if ($("#palette-overlay").classList.contains("open")) closePalette();
        else openPalette();
        return;
      }
      if (e.key === "Escape") {
        closePalette();
        closeDrawer();
        return;
      }
      if ($("#palette-overlay").classList.contains("open")) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          paletteMove(1);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          paletteMove(-1);
        } else if (e.key === "Enter") {
          e.preventDefault();
          paletteConfirm();
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (AE.CM) state.role = AE.CM.getRole();
    applyTheme();
    applyRole();
    bind();
    Promise.all([loadLiveMoney(), AE.polling.load(), AE.focusMap.loadGeo()]).then(refreshPollingViews);
    if (state.role === "cm") {
      renderCM();
      showPage("cm");
    } else {
      renderPortfolio();
      showPage("portfolio");
    }
  });
})();
