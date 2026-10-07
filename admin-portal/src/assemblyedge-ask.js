/** AssemblyEdge — optional Workers AI assist for /admin/assemblyedge/api/ask */

import { compactSocialFeedContext, loadSocialFeed } from "./assemblyedge-social-feed.js";

const DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct";
const DEFAULT_DAILY_LIMIT = 30;

const QUERY_SCHEMA_HINT = `{
  "intent": one of "precinct_swing" | "ie_week_spend" | "registration_compare" | "abev_mail_returns" | "precinct_margin_filter" | "district_roster" | "threat_index" | "polling_gap" | "late_money_district" | "social_posts" | "social_attacks" | "social_sentiment" | "unknown",
  "districtId": "ad-7" style lowercase id or null,
  "districtIdB": second district for compare or null,
  "place": city/place name string or null,
  "marginMaxPoints": number or null,
  "raceId": "g24_asm" | "g22_asm" or null,
  "direction": "toward_r" | "toward_d" or null,
  "candidateName": partial candidate last name or null,
  "flagFilter": "attack" | "ad" | "endorsement" | "event" | "policy" | "fundraising" | "spike" | null,
  "limit": number 1-50 or null
}`;

function utcDayKey() {
  return new Date().toISOString().slice(0, 10);
}

function aiEnabled(env) {
  const flag = (env.ASSEMBLYEDGE_ASK_AI || "true").toLowerCase();
  if (flag === "false" || flag === "0" || flag === "off") return false;
  return !!env.AI;
}

function dailyLimit(env) {
  const n = parseInt(String(env.ASSEMBLYEDGE_ASK_AI_DAILY_LIMIT || DEFAULT_DAILY_LIMIT), 10);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_DAILY_LIMIT;
}

function getUsage(session) {
  const u = session.assemblyedgeAskAi;
  if (!u || typeof u !== "object") return { day: utcDayKey(), count: 0 };
  return { day: u.day || utcDayKey(), count: Number(u.count) || 0 };
}

export function bumpAiUsage(session) {
  const today = utcDayKey();
  const prev = getUsage(session);
  const count = prev.day === today ? prev.count + 1 : 1;
  return { ...session, assemblyedgeAskAi: { day: today, count } };
}

export function aiQuotaRemaining(session, env) {
  if (!aiEnabled(env)) return 0;
  const today = utcDayKey();
  const prev = getUsage(session);
  const used = prev.day === today ? prev.count : 0;
  return Math.max(0, dailyLimit(env) - used);
}

/**
 * @param {import('./config.js').Env} env
 * @param {string} mode parse | summarize
 * @param {object} payload
 */
export async function runAssemblyEdgeAskAi(env, mode, payload) {
  if (!aiEnabled(env)) {
    return { ok: false, error: "ai_disabled", message: "Workers AI assist is disabled on this deployment." };
  }
  if (!env.AI || typeof env.AI.run !== "function") {
    return { ok: false, error: "ai_unavailable", message: "AI binding is not configured." };
  }

  const model = env.ASSEMBLYEDGE_ASK_AI_MODEL || DEFAULT_MODEL;

  if (mode === "parse") {
    const question = String(payload.question || "").trim();
    if (!question) {
      return { ok: false, error: "bad_request", message: "Missing question." };
    }
    const system = [
      "You translate natural-language questions about California Assembly district desk data into JSON only.",
      "Output MUST be a single JSON object matching this schema (no markdown, no prose):",
      QUERY_SCHEMA_HINT,
      "Use intent unknown if the question cannot map safely.",
      "districtId must be ad-N lowercase (e.g. ad-58).",
      "For swing questions use precinct_swing with direction toward_r or toward_d.",
      "For IE this week use ie_week_spend.",
      "For registration compare use registration_compare with two districts.",
      "For mail/ballot returns use abev_mail_returns.",
      "For tight precincts in a city use precinct_margin_filter with place and marginMaxPoints.",
      "For late contributions / Form 497 in a district use late_money_district with districtId.",
      "For who is the incumbent or Nov 2026 certified matchup use district_roster with districtId.",
      "For X/social posts by a candidate use social_posts with districtId and candidateName.",
      "For attack posts in a district use social_attacks with districtId (includes unverified mentions).",
      "For sentiment trend use social_sentiment with districtId.",
    ].join("\n");
    let socialContext = "";
    if (/social|\bx\b|twitter|post|attack|sentiment|gonzalez|hoover|murphy|wallis|castillo|davies|pacheco|cervantes|farias|slavensky|obeso|namvar/i.test(question)) {
      try {
        const loaded = await loadSocialFeed(env);
        if (loaded?.feed) {
          socialContext = "\n\n" + compactSocialFeedContext(loaded.feed);
        }
      } catch {
        /* optional context */
      }
    }
    let response;
    try {
      response = await env.AI.run(model, {
        messages: [
          { role: "system", content: system + socialContext },
          { role: "user", content: question },
        ],
        max_tokens: 256,
        temperature: 0.1,
      });
    } catch (err) {
      console.error("Workers AI parse failed:", err);
      return {
        ok: false,
        error: "ai_unavailable",
        message: "Workers AI is unavailable (quota or binding error). Use deterministic Ask in the browser.",
      };
    }
    const text = extractAiText(response);
    const parsed = extractJsonObject(text);
    if (!parsed) {
      return { ok: false, error: "ai_parse_failed", message: "Model did not return valid JSON." };
    }
    return { ok: true, query: parsed, model };
  }

  if (mode === "summarize") {
    const question = String(payload.question || "").trim();
    const result = payload.result;
    if (!result || typeof result !== "object") {
      return { ok: false, error: "bad_request", message: "Missing deterministic result payload." };
    }
    const system = [
      "You write a one- or two-sentence desk answer for campaign staff.",
      "CRITICAL: Use ONLY numbers and facts present in the provided JSON result. Never invent figures.",
      "If rows are empty, say data is unavailable in the bundle.",
      "Do not mention being an AI.",
    ].join("\n");
    const user = JSON.stringify({ question, result }, null, 0);
    let response;
    try {
      response = await env.AI.run(model, {
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
        max_tokens: 180,
        temperature: 0.2,
      });
    } catch (err) {
      console.error("Workers AI summarize failed:", err);
      return {
        ok: false,
        error: "ai_unavailable",
        message: "Workers AI phrasing unavailable.",
      };
    }
    const summary = extractAiText(response).trim();
    return { ok: true, summary, model };
  }

  return { ok: false, error: "bad_request", message: "Unknown mode." };
}

function extractAiText(response) {
  if (response == null) return "";
  if (typeof response === "string") return response;
  if (typeof response.response === "string") return response.response;
  if (response.result && typeof response.result.response === "string") return response.result.response;
  if (Array.isArray(response.messages)) {
    const last = response.messages[response.messages.length - 1];
    if (last && typeof last.content === "string") return last.content;
  }
  try {
    return JSON.stringify(response);
  } catch {
    return String(response);
  }
}

function extractJsonObject(text) {
  if (!text || typeof text !== "string") return null;
  const trimmed = text.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    /* fall through */
  }
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start >= 0 && end > start) {
    try {
      return JSON.parse(trimmed.slice(start, end + 1));
    } catch {
      return null;
    }
  }
  return null;
}

export function askApiMeta(env, session) {
  return {
    aiEnabled: aiEnabled(env),
    aiDailyLimit: dailyLimit(env),
    aiRemaining: aiQuotaRemaining(session, env),
  };
}
