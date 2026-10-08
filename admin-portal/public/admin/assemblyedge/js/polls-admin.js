/* MajorityIQ — internal poll intake (session + CSRF, mobile-friendly fields) */

(function () {
  "use strict";

  const cfg = window.__POLL_ADMIN__;
  if (!cfg) return;

  const statusEl = document.getElementById("poll-admin-status");
  const form = document.getElementById("poll-admin-form");
  const listEl = document.getElementById("poll-admin-list");
  const leadsEl = document.getElementById("poll-leads-list");
  const candidateHost = document.getElementById("candidate-rows");
  const districtSel = document.getElementById("district_id");

  let roster = null;

  function setStatus(msg, isErr) {
    if (statusEl) {
      statusEl.textContent = msg;
      statusEl.style.color = isErr ? "#f87171" : "";
    }
  }

  async function api(path, opts) {
    const res = await fetch(cfg.apiBase + path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...opts,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.message || json.error || "HTTP " + res.status);
    return json;
  }

  function districtCandidates(districtId) {
    if (!roster || !roster.districts) return [];
    const row = roster.districts.find((d) => d.id === districtId);
    if (!row) return [];
    if (row.open_seat) {
      return (row.general_candidates || []).slice(0, 2).map((c) => ({ name: c.name, party: c.party }));
    }
    const out = [];
    if (row.incumbent && row.incumbent.name) {
      out.push({ name: row.incumbent.name, party: row.incumbent.party });
    }
    const opp = (row.known_opponents || [])[0];
    if (opp && opp.name) out.push({ name: opp.name, party: opp.party });
    return out;
  }

  function candidateRowHtml(c, idx, extra) {
    const name = c.name || "";
    const party = c.party || "";
    const pct = c.pct != null ? c.pct : "";
    const extraCls = extra ? " candidate-row-extra" : "";
    const removeBtn = extra
      ? `<button type="button" class="btn" data-remove-row="${idx}" aria-label="Remove">×</button>`
      : "";
    return `<div class="candidate-row${extraCls}" data-cand-idx="${idx}">
      <div><label class="sr-only">Name</label><input type="text" data-cand-name value="${escapeAttr(name)}" ${extra ? "" : "readonly"} maxlength="120"></div>
      <div class="party-badge">${party || "—"}</div>
      <div><label class="sr-only">Percent</label><input type="number" data-cand-pct value="${pct}" min="0" max="100" step="0.1" inputmode="decimal" placeholder="%" required></div>
      ${removeBtn}
      <input type="hidden" data-cand-party value="${escapeAttr(party)}">
    </div>`;
  }

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function renderCandidateRows(districtId, toplines) {
    if (!candidateHost) return;
    const base = districtCandidates(districtId);
    const rows = [];
    if (toplines && toplines.length) {
      toplines.forEach((t, i) => {
        const extra = i >= base.length;
        rows.push(candidateRowHtml({ name: t.name, party: t.party, pct: t.pct }, i, extra));
      });
    } else {
      base.forEach((c, i) => rows.push(candidateRowHtml(c, i, false)));
      if (rows.length < 2) {
        rows.push(candidateRowHtml({ name: "", party: "D", pct: "" }, 1, true));
      }
    }
    candidateHost.innerHTML = rows.join("");
    bindCandidateRowEvents();
    updateSumHint();
  }

  function bindCandidateRowEvents() {
    candidateHost.querySelectorAll("[data-cand-pct]").forEach((inp) => {
      inp.addEventListener("input", updateSumHint);
    });
    document.getElementById("undecided_pct")?.addEventListener("input", updateSumHint);
    candidateHost.querySelectorAll("[data-remove-row]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const row = btn.closest(".candidate-row");
        row?.remove();
        updateSumHint();
      });
    });
  }

  function readToplinesFromDom() {
    const rows = candidateHost.querySelectorAll(".candidate-row");
    const out = [];
    rows.forEach((row) => {
      const name = row.querySelector("[data-cand-name]")?.value.trim();
      const party = row.querySelector("[data-cand-party]")?.value.trim().toUpperCase();
      const pct = Number(row.querySelector("[data-cand-pct]")?.value);
      if (!name) return;
      if (!party || (party !== "R" && party !== "D")) throw new Error("Each candidate needs party R or D.");
      if (!Number.isFinite(pct) || pct < 0 || pct > 100) throw new Error("Each candidate % must be 0–100.");
      out.push({ name, party, pct });
    });
    if (out.length < 2) throw new Error("Enter at least two candidates with percentages.");
    return out;
  }

  function updateSumHint() {
    const hint = document.getElementById("topline-sum-hint");
    if (!hint) return;
    try {
      const tops = readToplinesFromDom();
      const u = Number(document.getElementById("undecided_pct")?.value || 0);
      const sum = tops.reduce((s, t) => s + t.pct, 0) + (Number.isFinite(u) ? u : 0);
      hint.textContent =
        sum > 101
          ? `Sum ${sum.toFixed(1)}% — must be ≤101 before save.`
          : `Sum ${sum.toFixed(1)}% (candidate % + undecided must be ≤101).`;
      hint.style.color = sum > 101 ? "#f87171" : "";
    } catch {
      hint.textContent = "Candidate % + undecided must not exceed 101.";
      hint.style.color = "";
    }
  }

  function readForm() {
    const toplines = readToplinesFromDom();
    const undecidedRaw = document.getElementById("undecided_pct").value;
    let undecided_pct = null;
    if (undecidedRaw !== "") {
      undecided_pct = Number(undecidedRaw);
      if (!Number.isFinite(undecided_pct) || undecided_pct < 0 || undecided_pct > 100) {
        throw new Error("Undecided % must be 0–100.");
      }
    }
    const sum =
      toplines.reduce((s, t) => s + t.pct, 0) + (undecided_pct != null ? undecided_pct : 0);
    if (sum > 101) throw new Error("Toplines + undecided must sum to ≤101.");

    let crosstabs = null;
    const ct = document.getElementById("crosstabs").value.trim();
    if (ct) {
      try {
        crosstabs = JSON.parse(ct);
      } catch {
        throw new Error("Crosstabs must be valid JSON.");
      }
    }

    const sample_n = Number(document.getElementById("sample_n").value);
    if (!Number.isInteger(sample_n) || sample_n < 1) throw new Error("Sample n is required (integer > 0).");

    return {
      id: document.getElementById("poll-id").value || undefined,
      district_id: districtSel.value,
      pollster: document.getElementById("pollster").value.trim(),
      sponsor: document.getElementById("sponsor").value.trim() || null,
      sponsor_type: document.getElementById("sponsor_type").value,
      sponsor_party: document.getElementById("sponsor_party").value || null,
      field_start: document.getElementById("field_start").value,
      field_end: document.getElementById("field_end").value,
      sample_n,
      population: document.getElementById("population").value.trim() || null,
      mode: document.getElementById("mode").value.trim() || null,
      moe_pct: document.getElementById("moe_pct").value || null,
      undecided_pct: undecided_pct,
      toplines,
      crosstabs,
      verified_by: document.getElementById("verified_by").value.trim() || null,
      notes: document.getElementById("notes").value.trim() || null,
      _csrf: cfg.csrf,
    };
  }

  function fillForm(poll) {
    document.getElementById("poll-form-title").textContent = poll.id
      ? "Edit internal poll #" + poll.id
      : "Add internal poll";
    document.getElementById("poll-id").value = poll.id || "";
    districtSel.value = poll.district_id || "ad-7";
    renderCandidateRows(poll.district_id || districtSel.value, poll.toplines);
    document.getElementById("pollster").value = poll.pollster || "";
    document.getElementById("sponsor").value = poll.sponsor || "";
    document.getElementById("sponsor_type").value = poll.sponsor_type || "campaign";
    document.getElementById("sponsor_party").value = poll.sponsor_party || "";
    document.getElementById("field_start").value = poll.field_start || "";
    document.getElementById("field_end").value = poll.field_end || "";
    document.getElementById("sample_n").value = poll.sample_n != null ? poll.sample_n : "";
    document.getElementById("population").value = poll.population || "";
    document.getElementById("mode").value = poll.mode || "";
    document.getElementById("moe_pct").value = poll.moe_pct != null ? poll.moe_pct : "";
    document.getElementById("undecided_pct").value = poll.undecided_pct != null ? poll.undecided_pct : "";
    document.getElementById("crosstabs").value = poll.crosstabs ? JSON.stringify(poll.crosstabs, null, 2) : "";
    document.getElementById("verified_by").value = poll.verified_by || "";
    document.getElementById("notes").value = poll.notes || "";
    updateSumHint();
  }

  function renderList(polls) {
    if (!listEl) return;
    if (!polls.length) {
      listEl.innerHTML = "<li class='muted'>No internal polls saved.</li>";
      return;
    }
    listEl.innerHTML = polls
      .map((p) => {
        const tops = (p.toplines || [])
          .map((t) => `${t.name} (${t.party}) ${t.pct}%`)
          .join(" · ");
        return `<li>
          <strong>${p.district_code}</strong> · ${p.pollster} · field ${p.field_start} → ${p.field_end}
          <div class="muted">${tops}${p.undecided_pct != null ? " · Undecided " + p.undecided_pct + "%" : ""}</div>
          <div class="poll-row-actions">
            <button type="button" class="btn" data-edit="${p.id}">Edit</button>
            <button type="button" class="btn" data-del="${p.id}">Delete</button>
          </div>
        </li>`;
      })
      .join("");
    listEl.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const poll = polls.find((x) => String(x.id) === btn.dataset.edit);
        if (poll) fillForm(poll);
      });
    });
    listEl.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Delete internal poll #" + btn.dataset.del + "?")) return;
        try {
          await api("/internal/" + btn.dataset.del, {
            method: "DELETE",
            body: JSON.stringify({ _csrf: cfg.csrf }),
          });
          await refresh();
          setStatus("Deleted.");
        } catch (e) {
          setStatus(e.message, true);
        }
      });
    });
  }

  function renderLeads(leads) {
    if (!leadsEl) return;
    if (!leads.length) {
      leadsEl.innerHTML = "<li class='muted'>No leads on file — run scripts/update-released-polls.sh.</li>";
      return;
    }
    const sorted = leads.slice().sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    leadsEl.innerHTML = sorted
      .slice(0, 40)
      .map(
        (l) => `<li>
          <strong>${l.matched_district || "—"}</strong> · ${l.source || "—"} · ${l.date || "—"}
          <div><a href="${l.link}" target="_blank" rel="noopener noreferrer">${l.title || "Link"}</a></div>
          ${l.verification_note ? `<p class="muted" style="margin:6px 0 0">${l.verification_note}</p>` : ""}
          <button type="button" class="btn" data-promote='${encodeURIComponent(JSON.stringify(l))}'>Promote to form</button>
        </li>`,
      )
      .join("");
    leadsEl.querySelectorAll("[data-promote]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const lead = JSON.parse(decodeURIComponent(btn.dataset.promote));
        const did = lead.matched_district || districtSel.value;
        fillForm({
          district_id: did,
          pollster: "",
          sponsor_type: "campaign",
          field_start: lead.date || "",
          field_end: lead.date || "",
          notes: "Promoted from lead: " + (lead.title || "") + " " + (lead.link || ""),
          toplines: null,
        });
        setStatus("Lead loaded — enter verified toplines before save.");
      });
    });
  }

  async function loadLeadsFallback() {
    const url = cfg.leadsUrl || "data/polls/leads.json";
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) {
        const json = await res.json();
        return json.leads || [];
      }
    } catch {
      /* ignore */
    }
    return [];
  }

  async function refresh() {
    let polls = [];
    let leads = [];
    try {
      const data = await api("/admin-bundle", { method: "GET" });
      polls = data.polls || [];
      leads = data.leads || [];
    } catch {
      polls = [];
    }
    if (!leads.length) leads = await loadLeadsFallback();
    renderList(polls);
    renderLeads(leads);
  }

  districtSel?.addEventListener("change", () => {
    if (!document.getElementById("poll-id").value) {
      renderCandidateRows(districtSel.value, null);
    }
  });

  document.getElementById("add-candidate-row")?.addEventListener("click", () => {
    const idx = candidateHost.querySelectorAll(".candidate-row").length;
    const div = document.createElement("div");
    div.innerHTML = candidateRowHtml({ name: "", party: "D", pct: "" }, idx, true);
    candidateHost.appendChild(div.firstElementChild);
    bindCandidateRowEvents();
  });

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const body = readForm();
      const id = body.id;
      delete body.id;
      if (id) {
        await api("/internal/" + id, { method: "PUT", body: JSON.stringify(body) });
        setStatus("Updated poll #" + id);
      } else {
        const res = await api("/internal", { method: "POST", body: JSON.stringify(body) });
        setStatus("Created poll #" + res.id);
      }
      document.getElementById("poll-id").value = "";
      await refresh();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById("poll-form-reset")?.addEventListener("click", () => {
    document.getElementById("poll-id").value = "";
    fillForm({ district_id: districtSel.value, sponsor_type: "campaign" });
  });

  document.getElementById("poll-csv-import")?.addEventListener("click", async () => {
    const csv = document.getElementById("poll-csv").value;
    try {
      const res = await api("/internal/import-csv", {
        method: "POST",
        body: JSON.stringify({ csv, _csrf: cfg.csrf }),
      });
      setStatus("Imported " + res.imported + " poll(s).");
      await refresh();
    } catch (e) {
      setStatus(e.message, true);
    }
  });

  async function init() {
    const rosterUrl = cfg.rosterUrl || "data/calaccess/beachheads.json";
    try {
      const res = await fetch(rosterUrl, { cache: "no-store" });
      if (res.ok) roster = await res.json();
    } catch {
      roster = null;
    }
    renderCandidateRows(districtSel.value, null);
    refresh().catch((e) => setStatus(e.message, true));
  }

  init();
})();
