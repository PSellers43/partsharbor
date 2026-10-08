/** MajorityIQ — D1 internal polls (aggregate toplines only). */

export const INTERNAL_POLLS_MAX = 200;
export const INTERNAL_POLLS_WRITE_LIMIT = 60;
export const INTERNAL_POLLS_WRITE_WINDOW_MS = 60 * 60 * 1000;

const BEACHHEAD_IDS = new Set(["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"]);
const SPONSOR_TYPES = new Set(["independent", "campaign", "party", "ie"]);
const PARTIES = new Set(["R", "D"]);

function isIsoDate(s) {
  return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s);
}

function parseToplines(raw) {
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw);
    } catch {
      return { ok: false, error: "toplines must be JSON array." };
    }
  }
  if (!Array.isArray(raw) || raw.length < 2) {
    return { ok: false, error: "At least two candidate toplines required." };
  }
  const out = [];
  for (let i = 0; i < raw.length; i++) {
    const row = raw[i];
    if (!row || typeof row !== "object") {
      return { ok: false, error: `toplines[${i}] invalid.` };
    }
    const name = typeof row.name === "string" ? row.name.trim() : "";
    const party = typeof row.party === "string" ? row.party.trim().toUpperCase() : "";
    const pct = Number(row.pct);
    if (!name || name.length > 120) {
      return { ok: false, error: `toplines[${i}].name invalid.` };
    }
    if (!PARTIES.has(party)) {
      return { ok: false, error: `toplines[${i}].party must be R or D.` };
    }
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
      return { ok: false, error: `toplines[${i}].pct must be 0–100.` };
    }
    out.push({ name, party, pct: Math.round(pct * 10) / 10 });
  }
  return { ok: true, data: out };
}

function parseCrosstabs(raw) {
  if (raw == null || raw === "") return { ok: true, data: null };
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw);
    } catch {
      return { ok: false, error: "crosstabs must be JSON object of aggregate percentages." };
    }
  }
  if (typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, error: "crosstabs must be an object." };
  }
  const serialized = JSON.stringify(raw);
  if (new TextEncoder().encode(serialized).length > 12000) {
    return { ok: false, error: "crosstabs too large." };
  }
  return { ok: true, data: raw };
}

/**
 * @param {Record<string, unknown>} body
 */
export function validateInternalPollInput(body) {
  if (!body || typeof body !== "object") {
    return { ok: false, error: "Body must be an object." };
  }
  const districtId = typeof body.district_id === "string" ? body.district_id.trim() : "";
  if (!BEACHHEAD_IDS.has(districtId)) {
    return { ok: false, error: "district_id must be a beachhead id (ad-7 … ad-74)." };
  }
  const pollster = typeof body.pollster === "string" ? body.pollster.trim() : "";
  if (!pollster || pollster.length > 160) {
    return { ok: false, error: "pollster required (max 160 chars)." };
  }
  const sponsorType = typeof body.sponsor_type === "string" ? body.sponsor_type.trim() : "";
  if (!SPONSOR_TYPES.has(sponsorType)) {
    return { ok: false, error: "sponsor_type must be independent|campaign|party|ie." };
  }
  let sponsorParty = null;
  if (body.sponsor_party != null && body.sponsor_party !== "") {
    sponsorParty = String(body.sponsor_party).trim().toUpperCase();
    if (!PARTIES.has(sponsorParty)) {
      return { ok: false, error: "sponsor_party must be R or D when set." };
    }
  }
  const fieldStart = typeof body.field_start === "string" ? body.field_start.trim() : "";
  const fieldEnd = typeof body.field_end === "string" ? body.field_end.trim() : "";
  if (!isIsoDate(fieldStart) || !isIsoDate(fieldEnd)) {
    return { ok: false, error: "field_start and field_end must be YYYY-MM-DD." };
  }
  if (fieldEnd < fieldStart) {
    return { ok: false, error: "field_end must be on or after field_start." };
  }
  const toplines = parseToplines(body.toplines);
  if (!toplines.ok) return toplines;
  const crosstabs = parseCrosstabs(body.crosstabs);
  if (!crosstabs.ok) return crosstabs;

  let sampleN = null;
  if (body.sample_n != null && body.sample_n !== "") {
    sampleN = Number(body.sample_n);
    if (!Number.isInteger(sampleN) || sampleN < 1 || sampleN > 50000) {
      return { ok: false, error: "sample_n must be integer 1–50000." };
    }
  }
  let moe = null;
  if (body.moe_pct != null && body.moe_pct !== "") {
    moe = Number(body.moe_pct);
    if (!Number.isFinite(moe) || moe <= 0 || moe > 30) {
      return { ok: false, error: "moe_pct must be 0–30 when set." };
    }
  }
  let undecided = null;
  if (body.undecided_pct != null && body.undecided_pct !== "") {
    undecided = Number(body.undecided_pct);
    if (!Number.isFinite(undecided) || undecided < 0 || undecided > 100) {
      return { ok: false, error: "undecided_pct must be 0–100." };
    }
  }

  const strField = (k, max) => {
    const v = body[k];
    if (v == null || v === "") return null;
    if (typeof v !== "string") return { err: `${k} must be string.` };
    const t = v.trim();
    if (t.length > max) return { err: `${k} too long.` };
    return { val: t };
  };

  const sponsor = strField("sponsor", 240);
  if (sponsor && sponsor.err) return { ok: false, error: sponsor.err };
  const population = strField("population", 40);
  if (population && population.err) return { ok: false, error: population.err };
  const mode = strField("mode", 80);
  if (mode && mode.err) return { ok: false, error: mode.err };
  const sourceLabel = strField("source_label", 160);
  if (sourceLabel && sourceLabel.err) return { ok: false, error: sourceLabel.err };
  const sourceUrl = strField("source_url", 500);
  if (sourceUrl && sourceUrl.err) return { ok: false, error: sourceUrl.err };
  const notes = strField("notes", 500);
  if (notes && notes.err) return { ok: false, error: notes.err };
  const verifiedBy = strField("verified_by", 120);
  if (verifiedBy && verifiedBy.err) return { ok: false, error: verifiedBy.err };

  return {
    ok: true,
    data: {
      district_id: districtId,
      pollster,
      sponsor: sponsor?.val ?? null,
      sponsor_type: sponsorType,
      sponsor_party: sponsorParty,
      field_start: fieldStart,
      field_end: fieldEnd,
      sample_n: sampleN,
      population: population?.val ?? null,
      mode: mode?.val ?? null,
      moe_pct: moe,
      toplines: toplines.data,
      undecided_pct: undecided,
      crosstabs: crosstabs.data,
      source_label: sourceLabel?.val ?? null,
      source_url: sourceUrl?.val ?? null,
      notes: notes?.val ?? null,
      verified_by: verifiedBy?.val ?? null,
      visibility: "private",
    },
  };
}

export function rowToPollApi(row) {
  let toplines = [];
  let crosstabs = null;
  try {
    toplines = JSON.parse(String(row.toplines_json || "[]"));
  } catch {
    toplines = [];
  }
  if (row.crosstabs_json) {
    try {
      crosstabs = JSON.parse(String(row.crosstabs_json));
    } catch {
      crosstabs = null;
    }
  }
  return {
    id: row.id,
    district_id: row.district_id,
    district_code: "AD-" + String(row.district_id).split("-")[1],
    pollster: row.pollster,
    sponsor: row.sponsor,
    sponsor_type: row.sponsor_type,
    sponsor_party: row.sponsor_party,
    field_start: row.field_start,
    field_end: row.field_end,
    sample_n: row.sample_n,
    population: row.population,
    mode: row.mode,
    moe_pct: row.moe_pct,
    toplines,
    undecided_pct: row.undecided_pct,
    crosstabs,
    source_label: row.source_label,
    source_url: row.source_url,
    notes: row.notes,
    visibility: row.visibility,
    verified_by: row.verified_by,
    updated_at: row.updated_at,
    created_at: row.created_at,
  };
}

export async function listInternalPolls(db) {
  const rows = await db
    .prepare(
      `SELECT id, district_id, pollster, sponsor, sponsor_type, sponsor_party,
              field_start, field_end, sample_n, population, mode, moe_pct,
              toplines_json, undecided_pct, crosstabs_json, source_label, source_url,
              notes, visibility, verified_by, created_at, updated_at
       FROM majorityiq_internal_polls
       ORDER BY field_end DESC, id DESC
       LIMIT ?`,
    )
    .bind(INTERNAL_POLLS_MAX)
    .all();
  return (rows.results || []).map(rowToPollApi);
}

export async function countInternalPolls(db) {
  const row = await db.prepare(`SELECT COUNT(*) AS n FROM majorityiq_internal_polls`).first();
  return Number(row?.n ?? 0);
}

export async function insertInternalPoll(db, data, adminId) {
  const now = Date.now();
  const result = await db
    .prepare(
      `INSERT INTO majorityiq_internal_polls (
        district_id, pollster, sponsor, sponsor_type, sponsor_party,
        field_start, field_end, sample_n, population, mode, moe_pct,
        toplines_json, undecided_pct, crosstabs_json, source_label, source_url,
        notes, visibility, verified_by, created_by_admin_id, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      data.district_id,
      data.pollster,
      data.sponsor,
      data.sponsor_type,
      data.sponsor_party,
      data.field_start,
      data.field_end,
      data.sample_n,
      data.population,
      data.mode,
      data.moe_pct,
      JSON.stringify(data.toplines),
      data.undecided_pct,
      data.crosstabs ? JSON.stringify(data.crosstabs) : null,
      data.source_label,
      data.source_url,
      data.notes,
      data.visibility,
      data.verified_by,
      adminId ?? null,
      now,
      now,
    )
    .run();
  return Number(result.meta.last_row_id);
}

export async function updateInternalPoll(db, id, data) {
  const now = Date.now();
  await db
    .prepare(
      `UPDATE majorityiq_internal_polls SET
        district_id = ?, pollster = ?, sponsor = ?, sponsor_type = ?, sponsor_party = ?,
        field_start = ?, field_end = ?, sample_n = ?, population = ?, mode = ?, moe_pct = ?,
        toplines_json = ?, undecided_pct = ?, crosstabs_json = ?, source_label = ?, source_url = ?,
        notes = ?, verified_by = ?, updated_at = ?
       WHERE id = ?`,
    )
    .bind(
      data.district_id,
      data.pollster,
      data.sponsor,
      data.sponsor_type,
      data.sponsor_party,
      data.field_start,
      data.field_end,
      data.sample_n,
      data.population,
      data.mode,
      data.moe_pct,
      JSON.stringify(data.toplines),
      data.undecided_pct,
      data.crosstabs ? JSON.stringify(data.crosstabs) : null,
      data.source_label,
      data.source_url,
      data.notes,
      data.verified_by,
      now,
      id,
    )
    .run();
}

export async function deleteInternalPoll(db, id) {
  await db.prepare(`DELETE FROM majorityiq_internal_polls WHERE id = ?`).bind(id).run();
}

/** Rate limit poll writes per admin session (stored on session JSON). */
export function pollWriteQuotaRemaining(session) {
  const block = session.majorityiqPollWrites || { count: 0, windowStart: Date.now() };
  const now = Date.now();
  if (now - block.windowStart > INTERNAL_POLLS_WRITE_WINDOW_MS) {
    return INTERNAL_POLLS_WRITE_LIMIT;
  }
  return Math.max(0, INTERNAL_POLLS_WRITE_LIMIT - Number(block.count || 0));
}

export function bumpPollWriteUsage(session) {
  const now = Date.now();
  let block = session.majorityiqPollWrites || { count: 0, windowStart: now };
  if (now - block.windowStart > INTERNAL_POLLS_WRITE_WINDOW_MS) {
    block = { count: 0, windowStart: now };
  }
  block.count = Number(block.count || 0) + 1;
  session.majorityiqPollWrites = block;
  return session;
}

/**
 * Parse CSV (aggregate toplines): header district_id,pollster,sponsor_type,field_start,field_end,candidate_a,candidate_a_party,candidate_a_pct,...
 * Minimal supported columns documented in POLLS.md.
 */
export function parseInternalPollsCsv(text) {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return { ok: false, error: "CSV needs header + at least one row." };
  }
  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);
  const required = [
    "district_id",
    "pollster",
    "sponsor_type",
    "field_start",
    "field_end",
    "candidate_a",
    "candidate_a_party",
    "candidate_a_pct",
    "candidate_b",
    "candidate_b_party",
    "candidate_b_pct",
  ];
  for (const col of required) {
    if (idx(col) < 0) {
      return { ok: false, error: `CSV missing column ${col}.` };
    }
  }
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",").map((c) => c.trim());
    const body = {
      district_id: cols[idx("district_id")],
      pollster: cols[idx("pollster")],
      sponsor_type: cols[idx("sponsor_type")],
      sponsor: idx("sponsor") >= 0 ? cols[idx("sponsor")] : "",
      field_start: cols[idx("field_start")],
      field_end: cols[idx("field_end")],
      sample_n: idx("sample_n") >= 0 ? cols[idx("sample_n")] : "",
      moe_pct: idx("moe_pct") >= 0 ? cols[idx("moe_pct")] : "",
      undecided_pct: idx("undecided_pct") >= 0 ? cols[idx("undecided_pct")] : "",
      verified_by: idx("verified_by") >= 0 ? cols[idx("verified_by")] : "",
      toplines: [
        {
          name: cols[idx("candidate_a")],
          party: cols[idx("candidate_a_party")],
          pct: cols[idx("candidate_a_pct")],
        },
        {
          name: cols[idx("candidate_b")],
          party: cols[idx("candidate_b_party")],
          pct: cols[idx("candidate_b_pct")],
        },
      ],
    };
    const validated = validateInternalPollInput(body);
    if (!validated.ok) {
      return { ok: false, error: `Row ${i + 1}: ${validated.error}` };
    }
    rows.push(validated.data);
  }
  return { ok: true, data: rows };
}
