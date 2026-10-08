/* MajorityIQ — released + internal poll desk helpers */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.pollingDesk = AE.pollingDesk || {};
  AE.pollingReleased = null;
  AE.pollingInternal = [];
  AE.pollingLeads = null;
  AE.pollingDeskLoadError = null;

  const PARTISAN_TYPES = { campaign: true, party: true, ie: true };
  const PARTISAN_WEIGHT = 0.5;

  function parseDate(iso) {
    if (!iso) return null;
    const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function daysBetween(a, b) {
    return Math.floor((b.getTime() - a.getTime()) / 86400000);
  }

  function gapDays() {
    const r = AE.pollingReleased;
    const root = AE.pollingData;
    return (r && r.gap_recent_days) || (root && root.gap_recent_days) || 90;
  }

  function isRecentPoll(poll) {
    if (!poll || !poll.field_end) return false;
    const end = parseDate(poll.field_end);
    if (!end) return false;
    return daysBetween(end, new Date()) <= gapDays();
  }

  function marginFromToplines(toplines, undecided) {
    if (!toplines || toplines.length < 2) return null;
    const sorted = toplines.slice().sort((a, b) => (b.pct || 0) - (a.pct || 0));
    const leader = sorted[0];
    const trailer = sorted[1];
    const m = {
      leader_name: leader.name,
      leader_party: leader.party,
      leader_pct: leader.pct,
      trailer_name: trailer.name,
      trailer_party: trailer.party,
      trailer_pct: trailer.pct,
    };
    if (undecided != null) m.undecided_pct = undecided;
    return m;
  }

  AE.pollingDesk.sponsorChip = function (poll) {
    const t = poll.sponsor_type || "independent";
    if (t === "independent") return { cls: "chip-poll-live", label: "Independent" };
    if (t === "campaign") {
      const p = poll.sponsor_party ? " (" + poll.sponsor_party + ")" : "";
      return { cls: "chip-gap", label: "Campaign internal" + p };
    }
    if (t === "party") return { cls: "chip-gap", label: "Party / caucus" };
    if (t === "ie") return { cls: "chip-gap", label: "IE committee" };
    return { cls: "chip-demo", label: t };
  };

  AE.pollingDesk.releasedForDistrict = function (districtId) {
    const polls = (AE.pollingReleased && AE.pollingReleased.polls) || [];
    return polls.filter((p) => p.district_id === districtId).sort((a, b) => (b.field_end || "").localeCompare(a.field_end || ""));
  };

  AE.pollingDesk.internalForDistrict = function (districtId) {
    return (AE.pollingInternal || []).filter((p) => p.district_id === districtId);
  };

  AE.pollingDesk.allForDistrict = function (districtId) {
    const released = AE.pollingDesk.releasedForDistrict(districtId).map((p) => ({ ...p, visibility: "public" }));
    const internal = AE.pollingDesk.internalForDistrict(districtId).map((p) => ({ ...p, visibility: "private" }));
    return released.concat(internal).sort((a, b) => (b.field_end || "").localeCompare(a.field_end || ""));
  };

  AE.pollingDesk.bestRecentForDistrict = function (districtId) {
    const recent = AE.pollingDesk.allForDistrict(districtId).filter(isRecentPoll);
    return recent.length ? recent[0] : null;
  };

  AE.pollingDesk.pollBarsHtml = function (poll, compact) {
    const margin = poll.margin || marginFromToplines(poll.toplines, poll.undecided_pct);
    const recent = isRecentPoll(poll);
    const chip = AE.pollingDesk.sponsorChip(poll);
    const vis = poll.visibility === "private";
    if (!margin) {
      return `<div class="poll-gap-block"><div class="poll-gap-message">Toplines not verified</div></div>`;
    }
    const u = margin.undecided_pct || 0;
    const lead = margin.leader_party === "R" ? "r" : "d";
    const trail = margin.trailer_party === "R" ? "r" : "d";
    return `
      <div class="poll-bar-labels">
        <span>${margin.leader_name} (${margin.leader_party}) ${margin.leader_pct}%</span>
        <span>${margin.trailer_name} (${margin.trailer_party}) ${margin.trailer_pct}%</span>
        ${u ? `<span>Undecided ${u}%</span>` : ""}
      </div>
      <div class="poll-bar-track" aria-hidden="true">
        <span class="poll-bar-seg ${lead}" style="width:${margin.leader_pct}%"></span>
        <span class="poll-bar-seg ${trail}" style="width:${margin.trailer_pct}%"></span>
        ${u ? `<span class="poll-bar-seg u" style="width:${u}%"></span>` : ""}
      </div>
      <div class="poll-meta-chips">
        <span class="chip ${recent ? "chip-poll-live" : "chip-poll-stale"}">${recent ? "Recent" : "Stale · outside " + gapDays() + "d"}</span>
        <span class="chip ${chip.cls}">${chip.label}</span>
        ${vis ? `<span class="chip chip-gap">Internal (private)${poll.sponsor ? " — " + poll.sponsor : ""}</span>` : ""}
        <span class="chip chip-demo">${poll.pollster || "—"}</span>
        ${poll.moe_pct != null ? `<span class="chip chip-demo">±${poll.moe_pct}% MoE</span>` : ""}
        <span class="chip chip-demo">n=${poll.sample_n || "—"} ${poll.population || ""}</span>
        <span class="chip chip-demo">Field ${poll.field_start || "—"} → ${poll.field_end || "—"}</span>
      </div>
      ${poll.source_url ? `<a class="poll-source-link" href="${poll.source_url}" target="_blank" rel="noopener noreferrer">${poll.source_label || "Source"} ↗</a>` : ""}`;
  };

  AE.pollingDesk.districtBlockHtml = function (row, compact) {
    const polls = AE.pollingDesk.allForDistrict(row.id);
    const recent = polls.filter(isRecentPoll);
    const gapMsg = (row.gap && row.gap.message) || "No released poll in last 90 days";
    let body = "";
    if (recent.length) {
      body = recent
        .map(
          (p) => `<div class="poll-released-item">${AE.pollingDesk.pollBarsHtml(p, compact)}</div>`,
        )
        .join("");
    } else {
      body = `<div class="poll-gap-block"><div class="poll-gap-message">${gapMsg}</div></div>`;
    }
    const older = polls.filter((p) => !isRecentPoll(p));
    if (older.length && !compact) {
      body += `<details class="poll-older-details"><summary>Older polls (${older.length})</summary>${older
        .map((p) => `<div class="poll-released-item stale">${AE.pollingDesk.pollBarsHtml(p, compact)}</div>`)
        .join("")}</details>`;
    }
    return body;
  };

  AE.pollingDesk.leadsSectionHtml = function () {
    const leads = (AE.pollingLeads && AE.pollingLeads.leads) || [];
    if (!leads.length) {
      return `<div class="card method-card"><h3 class="card-title">Leads to verify <span class="chip chip-demo">Admin</span></h3><p class="muted">No RSS leads on file.</p></div>`;
    }
    const rows = leads
      .slice(0, 25)
      .map(
        (l) =>
          `<li><strong>${l.matched_district || "—"}</strong> · ${l.source || "—"} · ${l.date || "—"} — <a href="${l.link}" target="_blank" rel="noopener noreferrer">${l.title || "Link"}</a></li>`,
      )
      .join("");
    return `<div class="card method-card poll-leads-admin"><h3 class="card-title">Leads to verify <span class="chip chip-gap">Admin desk</span></h3><p style="font-size:12px;color:var(--text-muted)">Automated RSS candidates — verify before adding to <code>released.json</code>. <a href="/admin/majorityiq/polls-admin">Open intake form</a></p><ul class="poll-leads-list">${rows}</ul></div>`;
  };

  function pollMovementScore(poll) {
    const margin = poll.margin || marginFromToplines(poll.toplines, poll.undecided_pct);
    if (!margin) return null;
    const leader = margin.leader_party;
    const spread = Math.abs((margin.leader_pct || 0) - (margin.trailer_pct || 0));
    let base;
    if (leader === "D") base = 78 - Math.min(spread, 30);
    else if (leader === "R") base = 42 - Math.min(spread / 3, 12);
    else base = 50;
    const st = poll.sponsor_type || "independent";
    const partisan = !!PARTISAN_TYPES[st];
    if (partisan) base *= PARTISAN_WEIGHT;
    return { score: Math.round(base), partisan, sponsor_type: st };
  }

  AE.pollingDesk.applyThreatIndexRuntime = function () {
    if (!AE.intelLoaded || !AE.intelData || !AE.intelData.districts) return;
    const gap = gapDays();
    Object.keys(AE.intelData.districts).forEach((districtId) => {
      const best = AE.pollingDesk.bestRecentForDistrict(districtId);
      if (!best) return;
      const built = AE.pollingData && AE.polling.districtRow(districtId);
      const builtRecent = built && built.poll && AE.polling.isRecent(built.poll);
      const builtEnd = built && built.poll && built.poll.field_end;
      const bestEnd = best.field_end;
      if (builtRecent && builtEnd && bestEnd && builtEnd >= bestEnd && best.visibility !== "private") {
        return;
      }
      const mv = pollMovementScore(best);
      if (!mv) return;
      const row = AE.intelData.districts[districtId];
      const d = AE.districts.find((x) => x.id === districtId);
      if (!row || !d) return;
      const factors = row.factors || [];
      const pollsFactor = factors.find((f) => f.id === "polls");
      if (!pollsFactor) return;
      const blurb =
        (best.visibility === "private" ? "Internal (private) poll" : "Verified released poll") +
        ` (${best.pollster}, field end ${best.field_end}) — ${gap}-day window.` +
        (mv.partisan ? ` Partisan sponsor (${mv.sponsor_type}) — estimate at ${PARTISAN_WEIGHT * 100}% weight.` : " Independent — full weight.");
      pollsFactor.score = mv.score;
      pollsFactor.unavailable = false;
      pollsFactor.weight = pollsFactor.weight || 0.1875;
      pollsFactor.partisan_sponsor = mv.partisan;
      pollsFactor.blurb = blurb;
      pollsFactor.runtime_internal = best.visibility === "private";
      d.threatIndex = AE.pollingDesk.recomputeTiFromFactors(factors);
      AE.factors[districtId] = factors;
    });
  };

  AE.pollingDesk.recomputeTiFromFactors = function (factors) {
    const active = factors.filter((f) => !f.unavailable && f.score != null);
    let wSum = 0;
    active.forEach((f) => {
      wSum += f.weight || 0;
    });
    if (!wSum) return 50;
    let total = 0;
    active.forEach((f) => {
      total += ((f.weight || 0) / wSum) * f.score;
    });
    return Math.round(Math.min(100, Math.max(0, total)));
  };

  AE.pollingDesk.load = function () {
    AE.pollingReleased = null;
    AE.pollingInternal = [];
    AE.pollingLeads = null;
    const base = AE.polling.load ? AE.polling.load() : Promise.resolve();
    const released = fetch("data/polls/released.json", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        AE.pollingReleased = json;
      })
      .catch(() => {
        AE.pollingReleased = null;
      });
    const internal = fetch("./api/polls/internal", { credentials: "same-origin", cache: "no-store" })
      .then((res) => {
        if (res.status === 401) return { polls: [] };
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.pollingInternal = (json && json.polls) || [];
      })
      .catch(() => {
        AE.pollingInternal = [];
      });
    const leads = fetch("./api/polls/leads", { credentials: "same-origin", cache: "no-store" })
      .then(async (res) => {
        if (res.ok) return res.json();
        if (res.status === 401) {
          const fallback = await fetch("data/polls/leads.json", { cache: "no-store" });
          return fallback.ok ? fallback.json() : null;
        }
        return null;
      })
      .then((json) => {
        AE.pollingLeads = json;
      })
      .catch(async () => {
        try {
          const fallback = await fetch("data/polls/leads.json", { cache: "no-store" });
          AE.pollingLeads = fallback.ok ? await fallback.json() : null;
        } catch {
          AE.pollingLeads = null;
        }
      });
    return Promise.all([base, released, internal, leads]).catch((err) => {
      AE.pollingDeskLoadError = String(err && err.message ? err.message : err);
    });
  };
})();
