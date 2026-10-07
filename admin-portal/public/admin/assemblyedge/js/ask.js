/* MajorityIQ — Ask the desk (deterministic query layer + optional AI assist hook) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.ask = AE.ask || {};

  AE.ask.SUGGESTED = [
    "Which AD-7 precincts swung toward R between 2022 and 2024?",
    "How much IE money hit AD-58 this week?",
    "Compare registration mix in AD-47 vs AD-74.",
    "What were mail return rates in AD-36 in 2024?",
    "Which Rancho Cordova precincts are within 2 points?",
  ];

  AE.ask.config = {
    aiEnabled: false,
    aiRemaining: 0,
    aiDailyLimit: 30,
    csrfToken: null,
    preferAi: true,
  };

  /** @type {{ navigate?: Function, openPrecinct?: Function }} */
  const handlers = {};

  AE.ask.setHandlers = function (h) {
    if (h.navigate) handlers.navigate = h.navigate;
    if (h.openPrecinct) handlers.openPrecinct = h.openPrecinct;
  };

  AE.ask.apiBase = function () {
    const path = window.location.pathname || "";
    if (path.indexOf("/admin/majorityiq") === 0) return "/admin/majorityiq";
    if (path.indexOf("/admin/assemblyedge") === 0) return "/admin/assemblyedge";
    return "/admin/majorityiq";
  };

  AE.ask.fetchSessionMeta = function () {
    return fetch(AE.ask.apiBase() + "/api/csrf", { credentials: "same-origin", cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.ask.config.csrfToken = json.csrfToken || null;
        AE.ask.config.aiEnabled = !!json.aiEnabled;
        AE.ask.config.aiRemaining = json.aiRemaining != null ? json.aiRemaining : 0;
        AE.ask.config.aiDailyLimit = json.aiDailyLimit != null ? json.aiDailyLimit : 30;
        return json;
      })
      .catch(() => {
        AE.ask.config.csrfToken = null;
        AE.ask.config.aiEnabled = false;
        return null;
      });
  };

  function normalizeQuestion(q) {
    return String(q || "")
      .trim()
      .replace(/\s+/g, " ");
  }

  function parseDistrictId(text) {
    const m = /\bAD[\s-]?(\d{1,2})\b/i.exec(text);
    if (m) return "ad-" + parseInt(m[1], 10);
    const m2 = /\bad-(\d{1,2})\b/i.exec(text);
    if (m2) return "ad-" + parseInt(m2[1], 10);
    return null;
  }

  function parseDistrictPair(text) {
    const ids = [];
    const re = /\bAD[\s-]?(\d{1,2})\b/gi;
    let m;
    while ((m = re.exec(text))) {
      const id = "ad-" + parseInt(m[1], 10);
      if (ids.indexOf(id) < 0) ids.push(id);
    }
    if (ids.length >= 2) return [ids[0], ids[1]];
    return null;
  }

  function parsePlace(text) {
    const inMatch = /\bin\s+([A-Za-z][A-Za-z\s.'-]{2,40}?)(?:\s+precinct|\s+district|\s+are|\?|$)/i.exec(text);
    if (inMatch) return inMatch[1].trim();
    const which = /which\s+([A-Za-z][A-Za-z\s.'-]{2,40}?)\s+precinct/i.exec(text);
    if (which) return which[1].trim();
    return null;
  }

  function parseMarginMax(text) {
    const m = /within\s+(\d+(?:\.\d+)?)\s+points?/i.exec(text);
    if (m) return parseFloat(m[1]);
    const m2 = /(\d+(?:\.\d+)?)\s+points?\s+or\s+(?:closer|less)/i.exec(text);
    if (m2) return parseFloat(m2[1]);
    return null;
  }

  function parseLimit(text, fallback) {
    const m = /\btop\s+(\d{1,2})\b/i.exec(text);
    if (m) return Math.min(50, parseInt(m[1], 10));
    const m2 = /\bfirst\s+(\d{1,2})\b/i.exec(text);
    if (m2) return Math.min(50, parseInt(m2[1], 10));
    return fallback;
  }

  AE.ask.parseIntent = function (question) {
    const q = normalizeQuestion(question).toLowerCase();
    const original = normalizeQuestion(question);
    const districtId = parseDistrictId(original);
    const pair = parseDistrictPair(original);
    const place = parsePlace(original);
    const marginMax = parseMarginMax(original);
    const limit = parseLimit(original, 25);

    const towardR = /\btoward\s+r\b|\bswing.*\br\b|\brepublican\b.*\bswing\b|\br\+?\s*swing\b/.test(q);
    const towardD = /\btoward\s+d\b|\bswing.*\bd\b|\bdemocratic\b.*\bswing\b/.test(q) && !towardR;

    if (/(registration|registered|party mix|reg mix)/.test(q) && (pair || /\bvs\b|\bversus\b|\bcompare\b/.test(q))) {
      const ids = pair || (districtId ? [districtId, null] : [null, null]);
      return {
        intent: "registration_compare",
        districtId: ids[0],
        districtIdB: ids[1],
        limit,
        raw: original,
      };
    }

    if (/(mail|ballot|abev|vbm|return rate)/.test(q)) {
      const year = /\b2024\b/.test(q) ? "g24" : /\b2022\b/.test(q) ? "g22" : "g24";
      return {
        intent: "abev_mail_returns",
        districtId: districtId || parseDistrictId(q) || "ad-36",
        electionCode: year,
        limit,
      };
    }

    if (/(^|\s)ie\b|independent expenditure/.test(q) && /(week|this week|7d|7-day)/.test(q)) {
      return {
        intent: "ie_week_spend",
        districtId: districtId || "ad-58",
        limit: Math.min(limit, 15),
      };
    }

    if (/swung|swing|shift|moved/.test(q) && /(2022|2024|precinct)/.test(q)) {
      return {
        intent: "precinct_swing",
        districtId: districtId || "ad-7",
        direction: towardD ? "toward_d" : "toward_r",
        limit,
        raceFrom: "g22_asm",
        raceTo: "g24_asm",
      };
    }

    if (/(within|tight|toss-up|even|competitive)/.test(q) && marginMax != null && (place || /precinct/.test(q))) {
      return {
        intent: "precinct_margin_filter",
        districtId: districtId || "ad-7",
        place: place || "Rancho Cordova",
        marginMaxPoints: marginMax,
        raceId: /\b2022\b/.test(q) ? "g22_asm" : "g24_asm",
        limit,
      };
    }

    if (/threat index|\bti\b/.test(q) && districtId) {
      return { intent: "threat_index", districtId, limit: 1 };
    }

    if (/poll|polling|gap/.test(q) && districtId) {
      return { intent: "polling_gap", districtId, limit: 1 };
    }

    if (place && marginMax != null) {
      return {
        intent: "precinct_margin_filter",
        districtId: districtId || "ad-7",
        place,
        marginMaxPoints: marginMax,
        raceId: "g24_asm",
        limit,
      };
    }

    return { intent: "unknown", districtId, limit, raw: original };
  };

  function formatMoneyFull(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    const v = Number(n);
    if (v >= 1_000_000) return "$" + (v / 1_000_000).toFixed(2) + "M";
    if (v >= 1000) return "$" + Math.round(v).toLocaleString("en-US");
    return "$" + v.toFixed(0);
  }

  function districtLabel(id) {
    const d = AE.districts && AE.districts.find((x) => x.id === id);
    return d ? d.code : (id || "").toUpperCase().replace("AD-", "AD-");
  }

  function sourceMeta(label, asOf, url) {
    return { label, asOf: asOf || null, url: url || null };
  }

  function ensureElectionPrecincts(districtId) {
    if (!AE.electionHistory || !AE.electionHistory.loadPrecincts) return Promise.resolve(null);
    return AE.electionHistory.loadPrecincts(districtId);
  }

  function precinctRows(districtId) {
    const geo = AE.electionPrecinctGeo && AE.electionPrecinctGeo[districtId];
    if (!geo || !geo.features) return [];
    return geo.features.map((f) => f.properties || {});
  }

  AE.ask.executeQuery = function (query) {
    const q = query && query.intent ? query : AE.ask.parseIntent(String(query || ""));
    switch (q.intent) {
      case "precinct_swing":
        return execPrecinctSwing(q);
      case "ie_week_spend":
        return Promise.resolve(execIeWeekSpend(q));
      case "registration_compare":
        return Promise.resolve(execRegistrationCompare(q));
      case "abev_mail_returns":
        return Promise.resolve(execAbevMail(q));
      case "precinct_margin_filter":
        return execPrecinctMarginFilter(q);
      case "threat_index":
        return Promise.resolve(execThreat(q));
      case "polling_gap":
        return Promise.resolve(execPolling(q));
      default:
        return Promise.resolve({
          ok: false,
          title: "Could not map question",
          summary:
            "Try a beachhead AD (AD-7, 27, 36, 47, 58, 74) and a pattern like swing, IE this week, registration compare, mail returns, or tight precincts in a city.",
          rows: [],
          sources: [],
          mode: "deterministic",
          query: q,
        });
    }
  };

  function execPrecinctSwing(q) {
    const districtId = q.districtId || "ad-7";
    const limit = q.limit || 25;
    const towardR = q.direction !== "toward_d";

    return ensureElectionPrecincts(districtId).then(() => {
      const rows = [];
      precinctRows(districtId).forEach((p) => {
        const m22 = (p.g22_asm && p.g22_asm.margin_dem) != null ? Number(p.g22_asm.margin_dem) : null;
        const m24 = (p.g24_asm && p.g24_asm.margin_dem) != null ? Number(p.g24_asm.margin_dem) : null;
        if (m22 == null || m24 == null) return;
        const delta = m24 - m22;
        const toward = delta < -0.05 ? "R" : delta > 0.05 ? "D" : "even";
        if (towardR && toward !== "R") return;
        if (!towardR && toward !== "D") return;
        rows.push({
          precinct_id: p.precinct_id || p.srprec,
          place: p.place_primary || "—",
          margin_2022: m22,
          margin_2024: m24,
          swing_pts: Math.round(Math.abs(delta) * 10) / 10,
          toward,
          swing_label: AE.electionHistory.formatSwing(m22, m24),
        });
      });
      rows.sort((a, b) => (towardR ? a.margin_2024 - b.margin_2024 : b.margin_2024 - a.margin_2024));
      const top = rows.slice(0, limit);
      const idx = AE.electionHistoryIndex;
      return {
        ok: true,
        title: `${districtLabel(districtId)} precincts swinging toward ${towardR ? "R" : "D"} (2022→2024 Assembly)`,
        summary: `${top.length} of ${rows.length} precincts with a net shift toward ${towardR ? "R" : "D"} (showing up to ${limit}).`,
        columns: [
          { key: "precinct_id", label: "Precinct" },
          { key: "place", label: "Place" },
          { key: "margin_2022", label: "2022 margin (D−R pts)" },
          { key: "margin_2024", label: "2024 margin" },
          { key: "swing_label", label: "Swing" },
        ],
        rows: top,
        sources: [
          sourceMeta(
            "Election history · SWDB SR precinct SOV",
            idx && idx.updated_at,
            idx && idx.sources && idx.sources.swdb_g24
          ),
        ],
        deepLinks: top.slice(0, 5).map((r) => ({
          label: `Open ${r.precinct_id} on Focus map`,
          type: "focus-precinct",
          districtId,
          precinctId: r.precinct_id,
        })),
        mode: "deterministic",
        query: q,
      };
    });
  }

  function execPrecinctMarginFilter(q) {
    const districtId = q.districtId || "ad-7";
    const placeNeedle = String(q.place || "").toLowerCase();
    const maxPts = q.marginMaxPoints != null ? Number(q.marginMaxPoints) : 2;
    const raceId = q.raceId || "g24_asm";

    return ensureElectionPrecincts(districtId).then(() => {
      const rows = [];
      precinctRows(districtId).forEach((p) => {
        const place = (p.place_primary || "").toLowerCase();
        if (placeNeedle && place.indexOf(placeNeedle) < 0) return;
        const race = p[raceId];
        if (!race || race.margin_dem == null) return;
        const m = Number(race.margin_dem);
        if (Math.abs(m) > maxPts) return;
        rows.push({
          precinct_id: p.precinct_id || p.srprec,
          place: p.place_primary || "—",
          margin_dem: Math.round(m * 10) / 10,
          dem_pct: race.dem_pct,
          votes: race.votes_two_party,
          margin_chip: AE.electionHistory.marginChipMeta(m).label,
        });
      });
      rows.sort((a, b) => Math.abs(a.margin_dem) - Math.abs(b.margin_dem));
      const limit = q.limit || 25;
      const top = rows.slice(0, limit);
      return {
        ok: true,
        title: `${q.place || "Place"} precincts within ${maxPts} pts · ${districtLabel(districtId)} · ${AE.electionHistory.raceLabel(raceId)}`,
        summary: `${top.length} precinct${top.length === 1 ? "" : "s"} with |margin| ≤ ${maxPts} points.`,
        columns: [
          { key: "precinct_id", label: "Precinct" },
          { key: "place", label: "Place" },
          { key: "margin_dem", label: "Margin (D−R pts)" },
          { key: "dem_pct", label: "Dem %" },
          { key: "votes", label: "2-party votes" },
        ],
        rows: top,
        sources: [
          sourceMeta(
            "Election history · SWDB SR precinct SOV",
            AE.electionHistoryIndex && AE.electionHistoryIndex.updated_at
          ),
        ],
        deepLinks: top.slice(0, 5).map((r) => ({
          label: `Focus map · ${r.precinct_id}`,
          type: "focus-precinct",
          districtId,
          precinctId: r.precinct_id,
        })),
        mode: "deterministic",
        query: q,
      };
    });
  }

  function execIeWeekSpend(q) {
    const districtId = q.districtId || "ad-58";
    const root = AE.liveMoney;
    const dist = root && root.districts && root.districts[districtId];
    const asOf = root && (root.data_as_of || root.generated_at);
    if (!dist || !dist.ie || !dist.ie.length) {
      return {
        ok: false,
        title: `IE spend · ${districtLabel(districtId)}`,
        summary: "CAL-ACCESS money JSON not loaded or no IE rows for this district.",
        rows: [],
        sources: [sourceMeta("CAL-ACCESS money-by-district", asOf)],
        mode: "deterministic",
        query: q,
      };
    }
    let total = 0;
    const rows = dist.ie.map((row) => {
      const series = row.series || [];
      const weekAmt = series.length ? Number(series[series.length - 1]) : 0;
      total += weekAmt;
      return {
        committee: row.name,
        side: row.side || row.role || "—",
        week_spend: weekAmt,
        cycle_spend: row.spend,
        wow_pct: row.deltaSpend,
      };
    });
    rows.sort((a, b) => b.week_spend - a.week_spend);
    const limit = q.limit || 15;
    return {
      ok: true,
      title: `IE money · ${districtLabel(districtId)} · latest 7-day bucket`,
      summary: `${formatMoneyFull(total)} across ${rows.length} IE committees in the most recent week bucket (ingest series[7]).`,
      columns: [
        { key: "committee", label: "Committee" },
        { key: "side", label: "Side" },
        { key: "week_spend", label: "This week ($)" },
        { key: "cycle_spend", label: "Cycle spend ($)" },
      ],
      rows: rows.slice(0, limit).map((r) => ({
        ...r,
        week_spend: formatMoneyFull(r.week_spend),
        cycle_spend: formatMoneyFull(r.cycle_spend),
      })),
      totals: { ie_week_spend: total },
      sources: [
        sourceMeta(
          "CAL-ACCESS · S496 IE + Form 460 rollups",
          asOf,
          root.source && root.source.url
        ),
      ],
      deepLinks: [
        {
          label: `Open ${districtLabel(districtId)} · Money tab`,
          type: "district-tab",
          districtId,
          tab: "money",
        },
      ],
      mode: "deterministic",
      query: q,
    };
  }

  function execRegistrationCompare(q) {
    const a = q.districtId || (parseDistrictPair(q.raw || "") || [])[0];
    const b = q.districtIdB || (parseDistrictPair(q.raw || "") || [])[1];
    if (!a || !b) {
      return {
        ok: false,
        title: "Registration compare",
        summary: "Name two districts (e.g. AD-47 vs AD-74).",
        rows: [],
        sources: [],
        mode: "deterministic",
        query: q,
      };
    }
    const rowA = AE.demography && AE.demography.districtRow(a);
    const rowB = AE.demography && AE.demography.districtRow(b);
    const meta = AE.demography && AE.demography.meta();
    if (!rowA || !rowB) {
      return {
        ok: false,
        title: "Registration compare",
        summary: "Demography JSON missing rows for one or both districts.",
        rows: [],
        sources: [sourceMeta("Demography bundle", meta && meta.updated_at)],
        mode: "deterministic",
        query: q,
      };
    }
    const partiesA = (rowA.registration && rowA.registration.parties) || [];
    const partiesB = (rowB.registration && rowB.registration.parties) || [];
    const byId = (list, id) => list.find((p) => p.id === id || p.label === id);
    const ids = ["dem", "rep", "npp"];
    const rows = ids.map((id) => {
      const pa = byId(partiesA, id) || byId(partiesA, id === "dem" ? "Democratic" : id === "rep" ? "Republican" : "No party preference");
      const pb = byId(partiesB, id) || byId(partiesB, id === "dem" ? "Democratic" : id === "rep" ? "Republican" : "No party preference");
      const label = pa ? pa.label : pb ? pb.label : id.toUpperCase();
      const pctA = pa && pa.pct != null ? pa.pct : null;
      const pctB = pb && pb.pct != null ? pb.pct : null;
      return {
        party: label,
        [districtLabel(a) + "_pct"]: pctA,
        [districtLabel(b) + "_pct"]: pctB,
        delta_pts: pctA != null && pctB != null ? Math.round((pctA - pctB) * 10) / 10 : null,
      };
    });
    const regAsOf = meta && meta.sources && meta.sources.registration && meta.sources.registration.as_of;
    return {
      ok: true,
      title: `Registration mix · ${districtLabel(a)} vs ${districtLabel(b)}`,
      summary: "SOS Report of Registration party percents (public aggregates).",
      columns: [
        { key: "party", label: "Party" },
        { key: districtLabel(a) + "_pct", label: districtLabel(a) + " %" },
        { key: districtLabel(b) + "_pct", label: districtLabel(b) + " %" },
        { key: "delta_pts", label: "Δ pts (A−B)" },
      ],
      rows,
      sources: [
        sourceMeta(
          "CA SOS Report of Registration (via demography bundle)",
          regAsOf,
          meta && meta.sources && meta.sources.registration && meta.sources.registration.source_url
        ),
      ],
      deepLinks: [
        { label: `Focus · ${districtLabel(a)} demography`, type: "focus-map", districtId: a },
        { label: `Focus · ${districtLabel(b)} demography`, type: "focus-map", districtId: b },
      ],
      mode: "deterministic",
      query: q,
    };
  }

  function execAbevMail(q) {
    const districtId = q.districtId || "ad-36";
    const row = AE.abev && AE.abev.districtRow(districtId);
    const meta = AE.abev && AE.abev.meta();
    const code = q.electionCode === "g22" ? "g22" : "g24";
    const baseline = row && row.baselines && row.baselines[code];
    if (!baseline) {
      return {
        ok: false,
        title: `Mail returns · ${districtLabel(districtId)}`,
        summary: "ABEV baseline not found for that year.",
        rows: [],
        sources: [sourceMeta("ABEV / SWDB VBM baselines", meta && meta.updated_at)],
        mode: "deterministic",
        query: q,
      };
    }
    const parties = (baseline.party_returns || []).slice(0, 6);
    return {
      ok: true,
      title: `Mail ballot returns · ${districtLabel(districtId)} · ${baseline.election || code}`,
      summary: `${AE.abev.formatNumber(baseline.vbm_returned)} VBM ballots returned (${AE.abev.formatPct(baseline.vbm_pct_of_sov_registration)} of SOV registration in overlapping SR precincts). Turnout ${AE.abev.formatPct(baseline.turnout_pct)}.`,
      columns: [
        { key: "label", label: "Party" },
        { key: "count", label: "Returned" },
        { key: "pct", label: "% of returns" },
      ],
      rows: parties.map((p) => ({
        label: p.label,
        count: AE.abev.formatNumber(p.count),
        pct: AE.abev.formatPct(p.pct),
      })),
      totals: {
        vbm_returned: baseline.vbm_returned,
        vbm_pct_of_sov_registration: baseline.vbm_pct_of_sov_registration,
        turnout_pct: baseline.turnout_pct,
      },
      sources: [
        sourceMeta(
          "SWDB All_VBM + SOV aggregates (ABEV-style baselines)",
          meta && meta.updated_at,
          meta && meta.sources && meta.sources.swdb && meta.sources.swdb.home
        ),
      ],
      deepLinks: [{ label: `Open ${districtLabel(districtId)} on Focus map`, type: "focus-map", districtId }],
      mode: "deterministic",
      query: q,
    };
  }

  function execThreat(q) {
    const d = AE.districts.find((x) => x.id === q.districtId);
    if (!d) {
      return { ok: false, title: "Threat Index", summary: "District not in desk portfolio.", rows: [], sources: [], query: q };
    }
    return {
      ok: true,
      title: `${d.code} Threat Index (illustrative)`,
      summary: `TI ${d.threatIndex} · ${d.status} · ${d.lean}`,
      rows: [{ metric: "Threat Index", value: d.threatIndex, delta_7d: d.delta7d, status: d.status }],
      columns: [
        { key: "metric", label: "Metric" },
        { key: "value", label: "Value" },
        { key: "delta_7d", label: "7d Δ" },
        { key: "status", label: "Status" },
      ],
      sources: [sourceMeta("MajorityIQ desk (demo TI)", null)],
      deepLinks: [{ label: `Open ${d.code} war room`, type: "district-tab", districtId: d.id, tab: "threat" }],
      mode: "deterministic",
      query: q,
    };
  }

  function execPolling(q) {
    const row = AE.polling && AE.polling.districtRow(q.districtId);
    const root = AE.pollingData;
    if (!row) {
      return {
        ok: false,
        title: `Polling · ${districtLabel(q.districtId)}`,
        summary: "No polling row in latest.json.",
        rows: [],
        sources: [sourceMeta("Polling latest.json", root && root.updated_at)],
        query: q,
      };
    }
    const recent = row.poll && AE.polling.isRecent(row.poll);
    return {
      ok: true,
      title: `Polling · ${districtLabel(q.districtId)}`,
      summary: recent
        ? `Latest public poll: ${row.poll.pollster} (${row.poll.field_start}–${row.poll.field_end})`
        : `Gap: no public horse-race poll in the last ${AE.polling.getGapDays()} days.`,
      rows: [row],
      sources: [sourceMeta("Curated public polls", root && root.updated_at)],
      deepLinks: [{ label: "Open polling desk", type: "page", page: "polling" }],
      mode: "deterministic",
      query: q,
    };
  }

  function postAskApi(payload) {
    return fetch(AE.ask.apiBase() + "/api/ask", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, _csrf: AE.ask.config.csrfToken }),
    }).then((res) => res.json().then((body) => ({ status: res.status, body })));
  }

  AE.ask.runQuestion = function (question, opts) {
    opts = opts || {};
    let parsed = opts.structured || AE.ask.parseIntent(question);
    const useAi =
      opts.useAi !== false && AE.ask.config.preferAi && AE.ask.config.aiEnabled && AE.ask.config.csrfToken;

    function finishDeterministic(structured, aiNotice, mode) {
      return AE.ask.executeQuery(structured || parsed).then((result) => {
        result.question = question;
        if (aiNotice) result.aiNotice = aiNotice;
        if (mode) result.mode = mode;
        return result;
      });
    }

    function maybeAiParse() {
      if (!useAi || parsed.intent !== "unknown") {
        return Promise.resolve(parsed);
      }
      return postAskApi({ mode: "assist", question })
        .then(({ status, body }) => {
          if (status === 429) {
            return { parsed, notice: body.message || "AI daily quota reached." };
          }
          if (body.ok && body.query) {
            if (body.aiRemaining != null) AE.ask.config.aiRemaining = body.aiRemaining;
            return { parsed: body.query, notice: body.aiNotice, mode: "ai-assisted" };
          }
          return { parsed, notice: body.message || "AI parse unavailable." };
        })
        .catch(() => ({ parsed, notice: "AI assist unavailable (offline or static-only)." }));
    }

    function maybeAiSummarize(result) {
      if (!useAi || !opts.aiPhrase || !result.ok) return Promise.resolve(result);
      if (AE.ask.config.aiRemaining <= 0) return Promise.resolve(result);
      return postAskApi({ mode: "summarize", question, result })
        .then(({ status, body }) => {
          if (body.ok && body.summary) {
            result.summary = body.summary;
            result.mode = "ai-assisted";
          } else if (status === 429) {
            result.aiNotice = (result.aiNotice ? result.aiNotice + " " : "") + (body.message || "AI quota reached.");
          }
          return result;
        })
        .catch(() => result);
    }

    return maybeAiParse().then(({ parsed: p, notice, mode }) => {
      parsed = p;
      return finishDeterministic(parsed, notice, mode).then(maybeAiSummarize);
    });
  };

  AE.ask.followDeepLink = function (link) {
    if (!link || !handlers.navigate) return;
    if (link.type === "page") {
      handlers.navigate(link.page);
      return;
    }
    if (link.type === "district-tab") {
      handlers.navigate("district", { districtId: link.districtId, tab: link.tab || "threat" });
      return;
    }
    if (link.type === "focus-map" || link.type === "focus-precinct") {
      handlers.navigate("focus-map", { focusDrillId: link.districtId, preserveFocusDrill: true });
      if (link.type === "focus-precinct" && link.precinctId && handlers.openPrecinct) {
        handlers.openPrecinct(link.districtId, link.precinctId);
      }
    }
  };

  AE.ask.renderAnswerHtml = function (result) {
    if (!result) return "";
    const sources = (result.sources || [])
      .map((s) => {
        const asOf = s.asOf ? ` · as of ${s.asOf}` : "";
        if (s.url) return `<li><a href="${s.url}" target="_blank" rel="noopener">${s.label}</a>${asOf}</li>`;
        return `<li>${s.label}${asOf}</li>`;
      })
      .join("");
    const cols = result.columns || [];
    const rows = result.rows || [];
    let table = "";
    if (cols.length && rows.length) {
      const head = cols.map((c) => `<th>${c.label}</th>`).join("");
      const body = rows
        .map((row) => `<tr>${cols.map((c) => `<td>${row[c.key] != null ? row[c.key] : "—"}</td>`).join("")}</tr>`)
        .join("");
      table = `<div class="ask-table-wrap"><table class="ask-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    }
    const links = (result.deepLinks || [])
      .map(
        (l, i) =>
          `<button type="button" class="btn btn-ghost ask-deeplink" data-ask-link="${i}">${l.label}</button>`
      )
      .join("");
    const notice = result.aiNotice
      ? `<p class="ask-ai-notice"><span class="chip chip-demo">Notice</span> ${result.aiNotice}</p>`
      : "";
    const modeChip =
      result.mode === "ai-assisted"
        ? `<span class="chip chip-live">AI phrasing</span>`
        : `<span class="chip chip-demo">Deterministic</span>`;
    return `
      <article class="ask-answer-card">
        <header class="ask-answer-head">
          <h3 class="ask-answer-title">${result.title || "Answer"}</h3>
          ${modeChip}
        </header>
        <p class="ask-answer-summary">${result.summary || ""}</p>
        ${table}
        ${links ? `<div class="ask-deeplinks">${links}</div>` : ""}
        ${sources ? `<ul class="ask-sources">${sources}</ul>` : ""}
        ${notice}
      </article>`;
  };

  AE.ask.bindAnswerEl = function (rootEl, result) {
    if (!rootEl || !result) return;
    rootEl._askResult = result;
    rootEl.querySelectorAll(".ask-deeplink").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.getAttribute("data-ask-link"), 10);
        const link = result.deepLinks && result.deepLinks[idx];
        AE.ask.followDeepLink(link);
      });
    });
  };
})();
