/** MajorityIQ — validate and load X social digest (D1 or bundled seed). */

export const SOCIAL_FEED_MAX_BYTES = 750_000;
export const SOCIAL_FEED_ROW_ID = 1;
export const SENTIMENT_HISTORY_MAX_DAYS = 120;

const BEACHHEAD_CODES = new Set(["AD-7", "AD-27", "AD-36", "AD-47", "AD-58", "AD-74"]);
const SENTIMENT_LABELS = new Set(["positive", "neutral", "negative"]);

function isSentimentBucket(v) {
  if (v == null || typeof v !== "object" || Array.isArray(v)) return false;
  const n = Number(v.n);
  if (!Number.isFinite(n) || n < 0) return false;
  if (v.avg != null && (typeof v.avg !== "number" || v.avg < -1 || v.avg > 1)) return false;
  return true;
}

function trimSentimentHistory(history) {
  if (!Array.isArray(history)) return [];
  const byDate = new Map();
  for (const row of history) {
    if (!row || typeof row !== "object") continue;
    byDate.set(row.date, row);
  }
  const dates = [...byDate.keys()].sort();
  const keep = new Set(dates.slice(-SENTIMENT_HISTORY_MAX_DAYS));
  return history.filter((r) => r && keep.has(r.date));
}

function validatePostSentiment(post, label) {
  if (post.sentiment == null && post.sentiment_label == null) return null;
  if (typeof post.sentiment !== "number" || post.sentiment < -1 || post.sentiment > 1) {
    return `${label}: sentiment must be -1..1.`;
  }
  if (typeof post.sentiment_label !== "string" || !SENTIMENT_LABELS.has(post.sentiment_label)) {
    return `${label}: sentiment_label must be positive|neutral|negative.`;
  }
  return null;
}

/**
 * @param {unknown} raw
 * @returns {{ ok: true, data: object } | { ok: false, error: string }}
 */
export function validateSocialFeedPayload(raw) {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, error: "Payload must be a JSON object." };
  }
  const obj = /** @type {Record<string, unknown>} */ (raw);
  if (obj.schema !== 1) {
    return { ok: false, error: "schema must be 1." };
  }
  if (typeof obj.as_of !== "string" || !obj.as_of.trim()) {
    return { ok: false, error: "Missing as_of." };
  }
  if (typeof obj.districts !== "object" || obj.districts == null || Array.isArray(obj.districts)) {
    return { ok: false, error: "districts must be an object." };
  }
  const districts = /** @type {Record<string, unknown>} */ (obj.districts);
  for (const code of Object.keys(districts)) {
    if (!BEACHHEAD_CODES.has(code)) {
      return { ok: false, error: `Unexpected district key ${code}.` };
    }
    const block = districts[code];
    if (block == null || typeof block !== "object" || Array.isArray(block)) {
      return { ok: false, error: `${code} block invalid.` };
    }
    const posts = /** @type {{ posts?: unknown }} */ (block).posts;
    if (posts != null && !Array.isArray(posts)) {
      return { ok: false, error: `${code}.posts must be an array.` };
    }
    if (Array.isArray(posts)) {
      for (let i = 0; i < posts.length; i++) {
        const err = validatePostSentiment(posts[i], `${code}.posts[${i}]`);
        if (err) return { ok: false, error: err };
      }
    }
  }
  if (obj.mentions != null && !Array.isArray(obj.mentions)) {
    return { ok: false, error: "mentions must be an array when present." };
  }
  if (Array.isArray(obj.mentions)) {
    for (let i = 0; i < obj.mentions.length; i++) {
      const err = validatePostSentiment(obj.mentions[i], `mentions[${i}]`);
      if (err) return { ok: false, error: err };
    }
  }
  if (obj.sentiment_history != null) {
    if (!Array.isArray(obj.sentiment_history)) {
      return { ok: false, error: "sentiment_history must be an array." };
    }
    for (const row of obj.sentiment_history) {
      if (!row || typeof row !== "object") return { ok: false, error: "sentiment_history row invalid." };
      if (typeof row.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(row.date)) {
        return { ok: false, error: "sentiment_history.date must be YYYY-MM-DD." };
      }
      if (typeof row.district !== "string" || !BEACHHEAD_CODES.has(row.district)) {
        return { ok: false, error: "sentiment_history.district invalid." };
      }
      for (const key of ["candidate_posts", "mentions", "toward_r", "toward_d"]) {
        if (!isSentimentBucket(row[key])) {
          return { ok: false, error: `sentiment_history.${key} invalid.` };
        }
      }
      if (row.net != null && (typeof row.net !== "number" || row.net < -2 || row.net > 2)) {
        return { ok: false, error: "sentiment_history.net out of range." };
      }
    }
    obj.sentiment_history = trimSentimentHistory(obj.sentiment_history);
  }
  let serialized;
  try {
    serialized = JSON.stringify(obj);
  } catch {
    return { ok: false, error: "Payload is not JSON-serializable." };
  }
  const byteSize = new TextEncoder().encode(serialized).length;
  if (byteSize > SOCIAL_FEED_MAX_BYTES) {
    return { ok: false, error: `Payload too large (${byteSize} bytes; max ${SOCIAL_FEED_MAX_BYTES}).` };
  }
  return { ok: true, data: obj };
}

/**
 * @param {import('./config.js').Env} env
 */
export async function readSocialFeedFromD1(env) {
  if (!env.DB) return null;
  try {
    const row = await env.DB.prepare(
      "SELECT as_of, payload, updated_at, byte_size FROM majorityiq_social_feed WHERE id = ?",
    )
      .bind(SOCIAL_FEED_ROW_ID)
      .first();
    if (!row || typeof row.payload !== "string") return null;
    const bytes = new TextEncoder().encode(row.payload).length;
    if (bytes > SOCIAL_FEED_MAX_BYTES) {
      console.warn("D1 social feed row exceeds size cap; ignoring.");
      return null;
    }
    let parsed;
    try {
      parsed = JSON.parse(row.payload);
    } catch {
      console.warn("D1 social feed JSON parse failed.");
      return null;
    }
    const validated = validateSocialFeedPayload(parsed);
    if (!validated.ok) {
      console.warn("D1 social feed validation failed:", validated.error);
      return null;
    }
    return {
      feed: validated.data,
      meta: {
        source: "d1",
        as_of: row.as_of,
        updated_at: row.updated_at,
        byte_size: row.byte_size,
      },
    };
  } catch (err) {
    console.error("D1 social feed read failed:", err);
    return null;
  }
}

const BUNDLE_ASSET_PATH = "/admin/assemblyedge/data/social/latest/social-feed.json";

/**
 * @param {import('./config.js').Env} env
 */
export async function readSocialFeedFromBundle(env) {
  const assets = env.ASSETS;
  if (!assets) return null;
  try {
    const res = await assets.fetch(new Request(`https://assets.local${BUNDLE_ASSET_PATH}`));
    if (!res.ok) return null;
    const parsed = await res.json();
    const validated = validateSocialFeedPayload(parsed);
    if (!validated.ok) {
      console.warn("Bundled social feed validation failed:", validated.error);
      return null;
    }
    return {
      feed: validated.data,
      meta: {
        source: "bundle",
        as_of: validated.data.as_of,
        updated_at: null,
        byte_size: new TextEncoder().encode(JSON.stringify(validated.data)).length,
      },
    };
  } catch (err) {
    console.error("Bundled social feed read failed:", err);
    return null;
  }
}

/**
 * @param {import('./config.js').Env} env
 */
export async function loadSocialFeed(env) {
  const fromD1 = await readSocialFeedFromD1(env);
  if (fromD1) return fromD1;
  return readSocialFeedFromBundle(env);
}

/** Compact digest for Workers AI parse assist (no post bodies). */
export function compactSocialFeedContext(feed) {
  if (!feed || typeof feed !== "object") return "";
  const districts = feed.districts || {};
  const lines = [`Social digest as_of ${feed.as_of || "—"} (window ${feed.window_days || "?"}d).`];
  for (const code of ["AD-7", "AD-27", "AD-36", "AD-47", "AD-58", "AD-74"]) {
    const block = districts[code] || {};
    const posts = block.posts || [];
    const flags = {};
    posts.forEach((p) => {
      (p.flags || []).forEach((f) => {
        flags[f] = (flags[f] || 0) + 1;
      });
    });
    const flagStr = Object.keys(flags).length
      ? Object.entries(flags)
          .map(([k, v]) => `${k}:${v}`)
          .join(",")
      : "none";
    const noX = (block.no_x_presence || []).join("; ") || "—";
    lines.push(`${code}: ${posts.length} candidate posts; flags ${flagStr}; no X: ${noX}`);
  }
  const mentions = feed.mentions || [];
  const mentionAttacks = mentions.filter((m) => (m.flags || []).includes("attack")).length;
  lines.push(`Mentions (unverified): ${mentions.length} (${mentionAttacks} flagged attack).`);
  const hist = feed.sentiment_history || [];
  if (hist.length) {
    const latest = hist.filter((r) => r.district === "AD-36").slice(-3);
    if (latest.length) {
      lines.push(
        "Recent AD-36 sentiment net: " +
          latest.map((r) => `${r.date}=${r.net != null ? r.net : "n/a"}`).join(", "),
      );
    }
  }
  lines.push(
    "Map social questions to intent social_posts, social_attacks, or social_sentiment (districtId).",
  );
  return lines.join("\n");
}
