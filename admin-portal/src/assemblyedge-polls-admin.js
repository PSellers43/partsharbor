function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function renderPollsAdminPage({ csrfToken, username, deskPrefix }) {
  const prefix = deskPrefix || "/admin/majorityiq";
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <title>MajorityIQ internal polls · PartsHarbor Admin</title>
  <link rel="stylesheet" href="/admin/static/admin.css">
  <style>
    .poll-admin-grid { display: grid; gap: 16px; max-width: 960px; margin: 0 auto; padding: 12px 16px 32px; box-sizing: border-box; }
    .poll-admin-grid input, .poll-admin-grid select, .poll-admin-grid textarea { width: 100%; box-sizing: border-box; font-size: 16px; }
    .poll-admin-grid .field { margin-bottom: 14px; }
    .poll-admin-grid label { display: block; font-size: 13px; margin-bottom: 4px; }
    .candidate-row { display: grid; grid-template-columns: 1fr 56px 72px; gap: 8px; align-items: end; margin-bottom: 8px; }
    .candidate-row .party-badge { font-size: 12px; color: #8892a8; padding-bottom: 10px; }
    .candidate-row-extra { grid-template-columns: 1fr 56px 72px 36px; }
    .poll-row-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .poll-list { list-style: none; padding: 0; margin: 0; }
    .poll-list li { border: 1px solid var(--border, #334); border-radius: 8px; padding: 12px; margin-bottom: 10px; }
    .leads-list { font-size: 13px; }
    .muted { color: #8892a8; font-size: 13px; line-height: 1.45; }
    .csv-block { margin-top: 8px; }
    .csv-block textarea { min-height: 72px; font-family: ui-monospace, monospace; font-size: 12px; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
    @media (max-width: 480px) {
      .poll-admin-grid { padding: 8px 10px 24px; }
      .admin-header { flex-wrap: wrap; gap: 8px; }
      .candidate-row, .candidate-row-extra { grid-template-columns: 1fr; }
      .candidate-row .party-badge { padding-bottom: 0; }
    }
  </style>
</head>
<body>
<header class="admin-header">
  <div class="brand">MajorityIQ <span>Internal polls</span></div>
  <div>
    <a class="btn btn-ghost" href="${esc(prefix)}/">Back to desk</a>
    <a class="btn btn-ghost" href="/admin">Admin home</a>
  </div>
</header>
<main class="admin-main poll-admin-grid">
  <div class="card">
    <h1>Private poll intake</h1>
    <p class="subtitle">Signed in as ${esc(username)}. Enter aggregate horse-race toplines only — no respondent-level data, voter files, or PII. Public releases still go in <code>data/polls/released.json</code> (git).</p>
    <p id="poll-admin-status" class="muted" role="status"></p>
  </div>
  <div class="card">
    <h2 id="poll-form-title">Add internal poll</h2>
    <form id="poll-admin-form">
      <input type="hidden" name="id" id="poll-id" value="">
      <div class="field">
        <label for="district_id">District</label>
        <select id="district_id" name="district_id" required>
          <option value="ad-7">AD-7</option>
          <option value="ad-27">AD-27</option>
          <option value="ad-36">AD-36</option>
          <option value="ad-47">AD-47</option>
          <option value="ad-58">AD-58</option>
          <option value="ad-74">AD-74</option>
        </select>
      </div>
      <div class="field"><label for="pollster">Pollster</label><input id="pollster" required maxlength="160" autocomplete="off"></div>
      <div class="field"><label for="sponsor">Sponsor (optional)</label><input id="sponsor" maxlength="240" autocomplete="off"></div>
      <div class="field">
        <label for="sponsor_type">Sponsor type</label>
        <select id="sponsor_type" required>
          <option value="campaign">Campaign internal</option>
          <option value="independent">Independent / media / academic</option>
          <option value="party">Party / caucus</option>
          <option value="ie">IE committee</option>
        </select>
      </div>
      <div class="field">
        <label for="sponsor_party">Sponsor party (R/D, optional)</label>
        <select id="sponsor_party"><option value="">—</option><option value="R">R</option><option value="D">D</option></select>
      </div>
      <div class="field"><label for="field_start">Field start</label><input id="field_start" type="date" required></div>
      <div class="field"><label for="field_end">Field end</label><input id="field_end" type="date" required></div>
      <div class="field"><label for="sample_n">Sample n (required)</label><input id="sample_n" type="number" min="1" max="50000" required inputmode="numeric"></div>
      <div class="field"><label for="population">Population (LV/RV/A)</label><input id="population" maxlength="40" placeholder="LV"></div>
      <div class="field"><label for="mode">Mode</label><input id="mode" maxlength="80" placeholder="phone / online"></div>
      <div class="field"><label for="moe_pct">MoE ±%</label><input id="moe_pct" type="number" step="0.1" min="0" max="30" inputmode="decimal"></div>
      <fieldset class="field" id="toplines-fieldset">
        <legend>Candidate results (%)</legend>
        <div id="candidate-rows"></div>
        <button type="button" class="btn" id="add-candidate-row">+ Add candidate</button>
        <div class="field" style="margin-top:12px">
          <label for="undecided_pct">Undecided %</label>
          <input id="undecided_pct" type="number" step="0.1" min="0" max="100" inputmode="decimal" placeholder="0">
        </div>
        <p class="muted" id="topline-sum-hint">Candidate % + undecided must not exceed 101.</p>
      </fieldset>
      <details class="field">
        <summary>Crosstabs JSON (optional)</summary>
        <textarea id="crosstabs" rows="3" placeholder='{"by_party":{"D":{"R":42}}}' style="font-family:ui-monospace,monospace;font-size:12px"></textarea>
      </details>
      <div class="field"><label for="verified_by">Verified by</label><input id="verified_by" maxlength="120"></div>
      <div class="field"><label for="notes">Notes</label><textarea id="notes" maxlength="500" rows="2"></textarea></div>
      <div class="poll-row-actions">
        <button type="submit" class="btn btn-primary">Save internal poll</button>
        <button type="button" class="btn" id="poll-form-reset">Clear</button>
      </div>
    </form>
  </div>
  <div class="card csv-block">
    <h2>CSV import (alternate)</h2>
    <p class="muted">Columns: district_id, pollster, sponsor_type, field_start, field_end, candidate_a, candidate_a_party, candidate_a_pct, candidate_b, candidate_b_party, candidate_b_pct, optional sponsor, sample_n, moe_pct, undecided_pct, verified_by</p>
    <textarea id="poll-csv" placeholder="district_id,pollster,..."></textarea>
    <button type="button" class="btn" id="poll-csv-import">Import CSV</button>
  </div>
  <div class="card">
    <h2>Saved internal polls</h2>
    <ul id="poll-admin-list" class="poll-list"></ul>
  </div>
  <div class="card">
    <h2>Leads to verify</h2>
    <p class="muted">From build-time RSS (<code>data/polls/leads.json</code>). Promote fills the form — verify toplines before saving public releases.</p>
    <ul id="poll-leads-list" class="poll-list leads-list"></ul>
  </div>
</main>
<script>
window.__POLL_ADMIN__ = { csrf: ${JSON.stringify(csrfToken)}, apiBase: ${JSON.stringify(prefix + "/api/polls")}, rosterUrl: ${JSON.stringify(prefix + "/data/calaccess/beachheads.json")}, leadsUrl: ${JSON.stringify(prefix + "/data/polls/leads.json")} };
</script>
<script src="${esc(prefix)}/js/polls-admin.js"></script>
</body>
</html>`;
}
