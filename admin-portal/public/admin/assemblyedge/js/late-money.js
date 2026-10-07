/* Late money (Form 497 / 496) — FPPC 90-day election cycle */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.lateMoney = AE.lateMoney || {};
  AE.lateMoneyData = null;
  AE.lateMoneyLoadError = null;

  AE.lateMoney.districtRow = function (districtId) {
    const root = AE.lateMoneyData;
    if (!root || !root.districts) return null;
    return root.districts[districtId] || null;
  };

  AE.lateMoney.meta = function () {
    return AE.lateMoneyData || null;
  };

  AE.lateMoney.load = function () {
    AE.lateMoneyData = null;
    AE.lateMoneyLoadError = null;
    return fetch("data/calaccess/latest/late-money-by-district.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.lateMoneyData = json;
        AE.lateMoneyLoadError = null;
      })
      .catch((err) => {
        AE.lateMoneyData = null;
        AE.lateMoneyLoadError = String(err && err.message ? err.message : err);
      });
  };

  function esc(s) {
    return AE.CM && AE.CM.escapeHtml ? AE.CM.escapeHtml(String(s == null ? "" : s)) : String(s == null ? "" : s);
  }

  function fmtMoney(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return (
      "$" +
      Number(n).toLocaleString("en-US", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      })
    );
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso + "T12:00:00");
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/Los_Angeles" });
    } catch {
      return iso;
    }
  }

  function weeklySparkFromDaily(dailyBuckets) {
    const buckets = Array.isArray(dailyBuckets) ? dailyBuckets : [];
    if (!buckets.length) return [];
    const weeks = [];
    for (let i = 0; i < buckets.length; i += 7) {
      const slice = buckets.slice(i, i + 7);
      weeks.push(slice.reduce((s, b) => s + (Number(b.amount) || 0), 0));
    }
    return weeks;
  }

  function sparklineSvg(values, cls) {
    const series = Array.isArray(values) ? values : [];
    if (!series.length) return "";
    const w = 140;
    const h = 32;
    const max = Math.max(...series, 1);
    const step = w / Math.max(series.length - 1, 1);
    const pts = series
      .map((v, i) => {
        const x = i * step;
        const y = h - (Number(v) / max) * (h - 4) - 2;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
    return `<svg class="late-spark ${cls || ""}" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.75" points="${pts}"/></svg>`;
  }

  AE.lateMoney.briefLine = function (districtId) {
    const meta = AE.lateMoney.meta();
    const row = AE.lateMoney.districtRow(districtId);
    if (AE.lateMoneyLoadError) {
      return `Late money: bundle unavailable (${AE.lateMoneyLoadError}).`;
    }
    if (!row || !meta) {
      return "Late money: no district row in CAL-ACCESS late-money bundle.";
    }
    const t = row.totals || {};
    const win = row.window || {};
    const asOf = row.as_of_date || (meta.data_as_of || meta.generated_at || "").slice(0, 10);
    const asOfShort = asOf ? fmtDate(asOf) : "—";
    if (row.empty) {
      return (
        `Late money (Form 497/496, ${win.start || "—"}→${win.end || "—"}): ` +
        `no filed lines in the 90-day period yet (${row.linked_f497_filings || 0} linked F497 filings). As of ${asOfShort}.`
      );
    }
    return (
      `Late money (90-day FPPC period): ` +
      `${fmtMoney(t.period_contributions)} on ${t.period_contribution_reports || 0} Form 497 lines` +
      ` · last 24h ${fmtMoney(t.last_24h)} · 7d ${fmtMoney(t.seven_day)}` +
      ` · IE ${fmtMoney(t.ie_period)} (${t.ie_reports || 0} S496). As of ${asOfShort}.`
    );
  };

  AE.lateMoney.renderPanel = function (districtId, compact) {
    const meta = AE.lateMoney.meta();
    const row = AE.lateMoney.districtRow(districtId);
    if (AE.lateMoneyLoadError) {
      return `<p class="intel-teaser-desc">Late money unavailable (${esc(AE.lateMoneyLoadError)}).</p>`;
    }
    if (!row) {
      return `<p class="intel-teaser-desc">No late-money row for this beachhead.</p>`;
    }
    const t = row.totals || {};
    const win = row.window || {};
    const asOfIso = row.as_of_date || (meta && (meta.data_as_of || meta.generated_at || "").slice(0, 10));
    const asOfLabel = asOfIso ? fmtDate(asOfIso) : "—";
    const periodContrib = t.period_contributions != null ? t.period_contributions : t.window_contributions;
    const last24 = t.last_24h != null ? t.last_24h : t.daily;
    const iePeriod = t.ie_period != null ? t.ie_period : t.ie_window;

    const stats = `
      <div class="late-money-stats">
        <div class="late-stat"><span class="late-stat-label">Last 24h</span><span class="late-stat-val mono">${fmtMoney(last24)}</span></div>
        <div class="late-stat"><span class="late-stat-label">7-day</span><span class="late-stat-val mono">${fmtMoney(t.seven_day)}</span></div>
        <div class="late-stat"><span class="late-stat-label">90-day 497</span><span class="late-stat-val mono">${fmtMoney(periodContrib)}</span></div>
        <div class="late-stat"><span class="late-stat-label">90-day 496</span><span class="late-stat-val mono">${fmtMoney(iePeriod)}</span></div>
      </div>`;

    const weekSeries = weeklySparkFromDaily(row.daily_buckets);
    const spark = sparklineSvg(weekSeries.length ? weekSeries : row.sparkline, row.empty ? "is-flat" : "");

    const donors =
      row.top_donors && row.top_donors.length
        ? `<ol class="late-donor-list">${row.top_donors
            .map(
              (d) =>
                `<li><strong>${esc(d.name)}</strong> <span class="mono">${fmtMoney(d.amount)}</span>` +
                `${d.employer ? ` <span class="late-donor-meta">${esc(d.employer)}</span>` : ""}</li>`
            )
            .join("")}</ol>`
        : `<p class="late-empty-note">No late received contributions in the 90-day period yet.</p>`;

    const timelineLimit = compact ? 8 : 60;
    const recent =
      row.recent_contributions && row.recent_contributions.length
        ? `<div class="late-timeline-scroll"><ul class="late-timeline">${row.recent_contributions
            .slice(0, timelineLimit)
            .map((r) => {
              const dir = r.direction === "made" ? "Made" : r.direction === "received" ? "Received" : "497";
              const side =
                r.side === "support"
                  ? `<span class="chip chip-live" style="font-size:10px">Support</span>`
                  : r.side === "oppose"
                    ? `<span class="chip chip-warn" style="font-size:10px">Oppose</span>`
                    : "";
              const candLabel =
                r.candidate && String(r.candidate).toLowerCase() !== "unknown" ? r.candidate : null;
              const sub = candLabel ? ` → ${esc(candLabel)}` : "";
              return `<li class="late-timeline-item">
                <span class="late-timeline-date mono">${fmtDate(r.contrib_date)}</span>
                <span class="late-timeline-body"><strong>${esc(r.entity)}</strong> ${dir} ${esc(r.committee_name || "")}${sub} ${side}</span>
                <span class="late-timeline-amt mono">${fmtMoney(r.amount)}</span>
              </li>`;
            })
            .join("")}</ul></div>`
        : `<p class="late-empty-note">No Form 497 lines dated ${esc(win.start)}–${esc(win.end)}. Linked committees: ${row.linked_f497_filings || 0} F497 filings.</p>`;

    const ieBlock =
      row.recent_ie && row.recent_ie.length
        ? `<div class="late-ie-block"><h4 class="late-subhead">Late independent expenditures (496)</h4><ul class="late-timeline">${row.recent_ie
            .slice(0, compact ? 4 : 12)
            .map(
              (r) =>
                `<li class="late-timeline-item">
                  <span class="late-timeline-date mono">${fmtDate(r.exp_date)}</span>
                  <span class="late-timeline-body"><strong>${esc(r.name)}</strong> ${r.side === "oppose" ? "oppose" : r.side === "support" ? "support" : "IE"} ${esc(r.target)}</span>
                  <span class="late-timeline-amt mono">${fmtMoney(r.amount)}</span>
                </li>`
            )
            .join("")}</ul></div>`
        : "";

    return `
      <div class="late-money-panel ${compact ? "is-compact" : ""}">
        <div class="late-money-head">
          <div>
            <h3 class="card-title" style="margin:0">Late money <span class="chip chip-live">Form 497 / 496</span></h3>
            <p class="money-source-note" style="margin:6px 0 0">
              FPPC 90-day period · ${fmtDate(win.start)}–${fmtDate(win.end)} (Nov 3 general)
              · As of <strong>${asOfLabel}</strong> · SOS daily CAL-ACCESS
            </p>
          </div>
          <div class="late-spark-wrap" title="Weekly Form 497 totals across the 90-day period">${spark}</div>
        </div>
        ${stats}
        <div class="late-money-grid">
          <div class="late-money-col">
            <h4 class="late-subhead">Late contributions (full period)</h4>
            ${recent}
          </div>
          <div class="late-money-col">
            <h4 class="late-subhead">Top late donors (received)</h4>
            ${donors}
            ${ieBlock}
          </div>
        </div>
      </div>`;
  };
})();
