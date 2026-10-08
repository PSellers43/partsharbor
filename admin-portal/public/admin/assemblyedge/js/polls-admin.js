/* MajorityIQ — internal poll intake (session + CSRF) */

(function () {
  "use strict";

  const cfg = window.__POLL_ADMIN__;
  if (!cfg) return;

  const statusEl = document.getElementById("poll-admin-status");
  const form = document.getElementById("poll-admin-form");
  const listEl = document.getElementById("poll-admin-list");
  const leadsEl = document.getElementById("poll-leads-list");

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

  function readForm() {
    let toplines;
    try {
      toplines = JSON.parse(document.getElementById("toplines").value);
    } catch {
      throw new Error("Toplines must be valid JSON array.");
    }
    let crosstabs = null;
    const ct = document.getElementById("crosstabs").value.trim();
    if (ct) {
      try {
        crosstabs = JSON.parse(ct);
      } catch {
        throw new Error("Crosstabs must be valid JSON.");
      }
    }
    return {
      id: document.getElementById("poll-id").value || undefined,
      district_id: document.getElementById("district_id").value,
      pollster: document.getElementById("pollster").value.trim(),
      sponsor: document.getElementById("sponsor").value.trim() || null,
      sponsor_type: document.getElementById("sponsor_type").value,
      sponsor_party: document.getElementById("sponsor_party").value || null,
      field_start: document.getElementById("field_start").value,
      field_end: document.getElementById("field_end").value,
      sample_n: document.getElementById("sample_n").value || null,
      population: document.getElementById("population").value.trim() || null,
      mode: document.getElementById("mode").value.trim() || null,
      moe_pct: document.getElementById("moe_pct").value || null,
      undecided_pct: document.getElementById("undecided_pct").value || null,
      toplines,
      crosstabs,
      verified_by: document.getElementById("verified_by").value.trim() || null,
      notes: document.getElementById("notes").value.trim() || null,
      _csrf: cfg.csrf,
    };
  }

  function fillForm(poll) {
    document.getElementById("poll-form-title").textContent = poll.id ? "Edit internal poll #" + poll.id : "Add internal poll";
    document.getElementById("poll-id").value = poll.id || "";
    document.getElementById("district_id").value = poll.district_id;
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
    document.getElementById("toplines").value = JSON.stringify(poll.toplines || [], null, 2);
    document.getElementById("crosstabs").value = poll.crosstabs ? JSON.stringify(poll.crosstabs, null, 2) : "";
    document.getElementById("verified_by").value = poll.verified_by || "";
    document.getElementById("notes").value = poll.notes || "";
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
          await api("/internal/" + btn.dataset.del, { method: "DELETE", body: JSON.stringify({ _csrf: cfg.csrf }) });
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
    leadsEl.innerHTML = leads
      .slice(0, 40)
      .map(
        (l) => `<li>
          <strong>${l.matched_district || "—"}</strong> · ${l.source || "—"} · ${l.date || "—"}
          <div><a href="${l.link}" target="_blank" rel="noopener noreferrer">${l.title || "Link"}</a></div>
          <button type="button" class="btn" data-promote='${encodeURIComponent(JSON.stringify(l))}'>Promote to form</button>
        </li>`,
      )
      .join("");
    leadsEl.querySelectorAll("[data-promote]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const lead = JSON.parse(decodeURIComponent(btn.dataset.promote));
        fillForm({
          district_id: lead.matched_district || "ad-7",
          pollster: "(verify from source)",
          sponsor_type: "independent",
          field_start: lead.date || "",
          field_end: lead.date || "",
          notes: "Promoted from lead: " + (lead.title || "") + " " + (lead.link || ""),
          toplines: [
            { name: "Candidate A", party: "R", pct: 0 },
            { name: "Candidate B", party: "D", pct: 0 },
          ],
        });
        setStatus("Lead loaded — enter verified toplines before save.");
      });
    });
  }

  async function refresh() {
    const data = await api("/admin-bundle", { method: "GET" });
    renderList(data.polls || []);
    renderLeads(data.leads || []);
  }

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
    fillForm({ district_id: "ad-7", sponsor_type: "campaign", toplines: [] });
    document.getElementById("poll-id").value = "";
  });

  document.getElementById("poll-csv-import")?.addEventListener("click", async () => {
    const csv = document.getElementById("poll-csv").value;
    try {
      const res = await api("/internal/import-csv", { method: "POST", body: JSON.stringify({ csv, _csrf: cfg.csrf }) });
      setStatus("Imported " + res.imported + " poll(s).");
      await refresh();
    } catch (e) {
      setStatus(e.message, true);
    }
  });

  refresh().catch((e) => setStatus(e.message, true));
})();
