/* MajorityIQ — computed Threat Index + intel tabs (static JSON from build) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.intel = AE.intel || {};
  AE.intelData = null;
  AE.intelLoadError = null;
  AE.intelLoaded = false;
  AE.intelMaxSpend = null;

  function leanLabel(raw, meta) {
    if (!raw || raw === "—") return "Lean unavailable";
    const tag = meta && meta.source_label ? ` · ${meta.source_label}` : " · SOS 2024 SOV";
    let label = raw + tag;
    if (meta && meta.context_2026) {
      label += " · open seat 2026";
    }
    return label;
  }

  AE.intel.apply = function () {
    const root = AE.intelData;
    if (!root || !root.districts) return;
    AE.intelLoaded = true;

    Object.keys(root.districts).forEach((id) => {
      const row = root.districts[id];
      const d = AE.districts.find((x) => x.id === id);
      if (!d || !row) return;
      d.threatIndex = row.threatIndex;
      d.status = row.status;
      d.delta24h = row.delta24h;
      d.delta7d = row.delta7d;
      d.history_note = row.history_note;
      d.lean = leanLabel(row.lean, row.lean_meta);
      d.lean_meta = row.lean_meta;
    });

    AE.factors = AE.factors || {};
    Object.keys(root.districts).forEach((id) => {
      AE.factors[id] = root.districts[id].factors;
    });

    AE.narrative = root.narrative || {};
    AE.rival = root.rival || {};
    AE.alerts = root.alerts || {};
    AE.ads = AE.ads || {};
    BEACHHEADS.forEach((id) => {
      AE.ads[id] = null;
    });
    AE.adsUnavailable = root.ads_unavailable || {
      message: "No free, reliable ad data source yet for CA Assembly races.",
    };

    if (root.formula && root.inputs) {
      AE.intelMeta = { formula: root.formula, inputs: root.inputs, generated_at: root.generated_at, as_of_date: root.as_of_date };
    }

    AE.DEMO_BANNER =
      "Real public data, refreshed manually — each panel shows its as-of time (PT). Estimates are tagged EST. " +
      "Synthetic/illustrative items are tagged DEMO. Threat Index, news, rival, and alerts from CAL-ACCESS + build-time Google News RSS; " +
      "2024 lean from CA SOS Statement of Vote. Ad data: see Ads tab. Not official FPPC/SOS/caucus figures.";
    const bannerEl = document.querySelector(".demo-banner-text");
    if (bannerEl) bannerEl.textContent = AE.DEMO_BANNER;
  };

  const BEACHHEADS = ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"];

  AE.intel.computeMaxSpend = function () {
    const live = AE.liveMoney && AE.liveMoney.districts;
    if (!live) return null;
    let max = 0;
    BEACHHEADS.forEach((id) => {
      const dist = live[id];
      if (!dist || !dist.live) return;
      const spend = [...(dist.candidates || []), ...(dist.ie || [])].reduce((s, r) => s + (r.spend || 0), 0);
      if (spend > max) max = spend;
    });
    AE.intelMaxSpend = max > 0 ? max : null;
    return AE.intelMaxSpend;
  };

  AE.intel.cmPrioritiesForDistrict = function (districtId) {
    const d = AE.districts.find((x) => x.id === districtId);
    const late = AE.lateMoney && AE.lateMoney.districtRow ? AE.lateMoney.districtRow(districtId) : null;
    const totals = (late && late.totals) || {};
    const ie7 = totals.ie_seven_day || 0;
    const news = (AE.narrative && AE.narrative[districtId]) || [];
    const recentNews = news.filter((n) => n.pub_date).length;
    const pollRow = AE.polling && AE.polling.districtRow ? AE.polling.districtRow(districtId) : null;
    const pollGap = pollRow && (!pollRow.poll || !AE.polling.isRecent(pollRow.poll));

    const out = [];

    if (ie7 >= 75000) {
      out.push({
        id: "ie-" + districtId,
        horizon: "24h",
        title: "Review anti-R IE pressure",
        detail: `7-day IE ${ie7 >= 1000 ? "$" + Math.round(ie7).toLocaleString("en-US") : ie7} in late-money window — verify filings before counter-spend.`,
        actions: ["money"],
        evidence: ["cm-craft", "issenberg"],
        alertId: null,
        urgency: "high",
      });
    }

    if (recentNews >= 2 || d.status === "elevated") {
      out.push({
        id: "msg-" + districtId,
        horizon: "24h",
        title: "Earned media / narrative scan",
        detail: "Check News tab headlines and prep one validated rapid-response line if a cluster forms.",
        actions: ["message", "rapid"],
        evidence: ["cm-craft"],
        alertId: null,
        urgency: d.status === "elevated" ? "high" : "medium",
      });
    }

    if (pollGap) {
      out.push({
        id: "poll-" + districtId,
        horizon: "48h",
        title: "Polling gap discipline",
        detail: (pollRow && pollRow.gap && pollRow.gap.message) || "No recent public horse-race poll — do not treat stale numbers as movement.",
        actions: ["message"],
        evidence: ["issenberg"],
        alertId: null,
        urgency: "medium",
      });
    }

    const abevRow = AE.abev && AE.abev.districtRow ? AE.abev.districtRow(districtId) : null;
    if (abevRow && abevRow.live && abevRow.live.returned != null) {
      out.push({
        id: "ev-" + districtId,
        horizon: "48h",
        title: "Ballot chase pulse",
        detail: "Live ballot returns posted — align chase lists to public ABEV feed (not a voter file).",
        actions: ["field"],
        evidence: ["green-gerber", "cm-craft"],
        alertId: null,
        urgency: "medium",
      });
    } else {
      out.push({
        id: "ev-gap-" + districtId,
        horizon: "72h",
        title: "ABEV / mail chase planning",
        detail: "2026 live returns not published or partial — use historical SWDB pace until SOS updates.",
        actions: ["field"],
        evidence: ["green-gerber"],
        alertId: null,
        urgency: "low",
      });
    }

    out.push({
      id: "cal-" + districtId,
      horizon: "72h",
      title: "CAL-ACCESS filing watch",
      detail: "Re-check Money + late-money after next SOS daily ZIP (weekday ingest).",
      actions: ["money"],
      evidence: ["cm-craft"],
      alertId: null,
      urgency: "low",
    });

    return out.slice(0, 6);
  };

  AE.intel.load = function () {
    AE.intelData = null;
    AE.intelLoadError = null;
    AE.intelLoaded = false;
    return fetch("data/threat-index/latest/threat-index-by-district.json", { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((json) => {
        AE.intelData = json;
        AE.intelLoadError = null;
        AE.intel.apply();
      })
      .catch((err) => {
        AE.intelData = null;
        AE.intelLoadError = String(err && err.message ? err.message : err);
        AE.intelLoaded = false;
      });
  };
})();
