import { Hono } from "hono";
import { getCookie, setCookie, deleteCookie } from "hono/cookie";
import { getConfig } from "./config.js";
import { verifyLogin, normalizeUsername } from "./auth.js";
import { countAdmins } from "./db.js";
import {
  destroySession,
  getSession,
  setSession,
  touchSession,
} from "./db.js";
import { resolveCsrfToken, validateCsrfSubmission } from "./csrf.js";
import {
  applyAssemblyEdgeSecurityHeaders,
  applySecurityHeaders,
} from "./security-headers.js";
import {
  askApiMeta,
  bumpAiUsage,
  aiQuotaRemaining,
  runAssemblyEdgeAskAi,
} from "./assemblyedge-ask.js";
import {
  htmlResponse,
  renderDashboard,
  renderError,
  renderLogin,
} from "./templates.js";

/** @typedef {import('./config.js').Env} Env */

const app = new Hono();

function clientIp(c) {
  return (
    c.req.header("CF-Connecting-IP") ||
    c.req.header("X-Forwarded-For")?.split(",")[0]?.trim() ||
    "127.0.0.1"
  );
}

function safeNextPath(raw) {
  if (typeof raw !== "string" || !raw.startsWith("/admin") || raw.startsWith("//")) {
    return null;
  }
  return raw;
}

function maskSessionId(sid) {
  if (!sid || sid.length < 8) return "—";
  return `${sid.slice(0, 4)}…${sid.slice(-4)}`;
}

function newSessionId() {
  return crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "");
}

function htmlBody(c, content, status = 200) {
  return c.body(content, status, { "Content-Type": "text/html; charset=utf-8" });
}

function cookieOpts(config, maxAgeSec) {
  return {
    path: "/",
    httpOnly: true,
    secure: config.isProduction,
    sameSite: "Strict",
    maxAge: maxAgeSec,
  };
}

app.use("*", async (c, next) => {
  const url = new URL(c.req.url);
  let config;
  try {
    config = getConfig(c.env, url);
  } catch (err) {
    const html = renderError({
      title: "Configuration error",
      message: err instanceof Error ? err.message : "Invalid configuration",
      status: 500,
    });
    const res = c.body(html, 500, { "Content-Type": "text/html; charset=utf-8" });
    applySecurityHeaders(c.res.headers, url.protocol === "https:");
    return res;
  }
  c.set("config", config);

  let sid = getCookie(c, config.sessionCookieName);
  if (!sid) {
    sid = newSessionId();
    setCookie(c, config.sessionCookieName, sid, cookieOpts(config, config.sessionMaxAgeMs / 1000));
  }

  let session = (await getSession(c.env.DB, sid)) ?? {};
  if (!session.createdAt) {
    session.createdAt = Date.now();
    await setSession(c.env.DB, sid, session, config.sessionMaxAgeMs);
  } else {
    await touchSession(c.env.DB, sid, config.sessionMaxAgeMs);
  }

  const csrf = resolveCsrfToken(
    c.req.raw,
    sid,
    config.sessionSecret,
    config.csrfCookieName,
    false,
    false,
  );
  if (!csrf.valid) {
    return htmlBody(
      c,
      renderError({
        title: "Forbidden",
        message: "Your session expired or the request was invalid. Refresh and try again.",
        status: 403,
      }),
      403,
    );
  }

  setCookie(c, config.csrfCookieName, csrf.cookieValue, cookieOpts(config, config.sessionMaxAgeMs / 1000));

  c.set("sid", sid);
  c.set("session", session);
  c.set("csrfToken", csrf.csrfToken);
  await next();
  applySecurityHeaders(c.res.headers, config.isProduction);
});

app.get("/healthz", (c) => {
  const headers = new Headers({ "Content-Type": "text/plain" });
  applySecurityHeaders(headers, c.get("config").isProduction);
  return new Response("ok", { headers });
});

app.get("/", (c) => c.redirect("/admin", 302));

app.get("/admin/login", async (c) => {
  const session = c.get("session");
  const config = c.get("config");
  if (session.admin?.id) {
    const next = safeNextPath(c.req.query("next"));
    return c.redirect(next || "/admin", 302);
  }
  return htmlBody(
    c,
    renderLogin({
      title: "Admin sign in",
      error: null,
      next: safeNextPath(c.req.query("next")),
      csrfToken: c.get("csrfToken"),
    }),
  );
});

app.post("/admin/login", async (c) => {
  const config = c.get("config");
  const sid = c.get("sid");
  const body = await c.req.parseBody();
  const csrfBody = typeof body._csrf === "string" ? body._csrf : "";

  if (
    !validateCsrfSubmission(
      c.req.raw,
      sid,
      config.sessionSecret,
      config.csrfCookieName,
      csrfBody,
    )
  ) {
    return htmlBody(
      c,
      renderError({
        title: "Forbidden",
        message: "Your session expired or the request was invalid. Refresh and try again.",
        status: 403,
      }),
      403,
    );
  }

  const username = typeof body.username === "string" ? body.username : "";
  const password = typeof body.password === "string" ? body.password : "";

  if ((await countAdmins(c.env.DB)) === 0) {
    return htmlBody(
      c,
      renderLogin({
        title: "Admin sign in",
        error: "Admin access is not configured yet. Run the bootstrap script (see ADMIN.md).",
        next: null,
        csrfToken: c.get("csrfToken"),
      }),
      503,
    );
  }

  const result = await verifyLogin(c.env.DB, config, username, password, clientIp(c));

  if (!result.ok) {
    const error =
      result.reason === "rate_limited"
        ? "Too many login attempts. Try again later."
        : "Invalid username or password.";
    return htmlBody(
      c,
      renderLogin({
        title: "Admin sign in",
        error,
        next: safeNextPath(typeof body.next === "string" ? body.next : null),
        csrfToken: c.get("csrfToken"),
      }),
      401,
    );
  }

  const oldSid = sid;
  const newSid = newSessionId();
  await destroySession(c.env.DB, oldSid);

  const newSession = {
    createdAt: Date.now(),
    admin: { id: result.admin.id, username: result.admin.username },
  };
  await setSession(c.env.DB, newSid, newSession, config.sessionMaxAgeMs);

  const csrf = resolveCsrfToken(
    c.req.raw,
    newSid,
    config.sessionSecret,
    config.csrfCookieName,
    true,
    false,
  );

  setCookie(c, config.sessionCookieName, newSid, cookieOpts(config, config.sessionMaxAgeMs / 1000));
  setCookie(c, config.csrfCookieName, csrf.cookieValue, cookieOpts(config, config.sessionMaxAgeMs / 1000));

  const destination = safeNextPath(typeof body.next === "string" ? body.next : null) || "/admin";
  return c.redirect(destination, 302);
});

app.get("/admin", async (c) => {
  const session = c.get("session");
  const config = c.get("config");
  if (!session.admin?.id) {
    return c.redirect(`/admin/login?next=${encodeURIComponent("/admin")}`, 302);
  }
  const expires = new Date(Date.now() + config.sessionMaxAgeMs);
  return htmlBody(
    c,
    renderDashboard({
      title: "Admin",
      csrfToken: c.get("csrfToken"),
      sessionMeta: {
        username: session.admin.username,
        sessionId: maskSessionId(c.get("sid")),
        expires,
      },
    }),
  );
});

/** Legacy URL prefix (static assets on disk). MajorityIQ is the product name. */
const ASSEMBLYEDGE_PREFIX = "/admin/assemblyedge";
/** Canonical alias — same authenticated app, rewritten to legacy asset paths. */
const MAJORITYIQ_PREFIX = "/admin/majorityiq";

async function serveMajorityIQDesk(c) {
  const session = c.get("session");
  const config = c.get("config");
  if (!session.admin?.id) {
    return c.redirect(
      `/admin/login?next=${encodeURIComponent(new URL(c.req.url).pathname)}`,
      302,
    );
  }

  /** @type {Fetcher | undefined} */
  const assets = c.env.ASSETS;
  if (!assets) {
    return htmlBody(
      c,
      renderError({
        title: "Error",
        message: "Static assets are not configured on this Worker.",
        status: 500,
      }),
      500,
    );
  }

  const incoming = new URL(c.req.url);
  let assetPath = incoming.pathname;
  if (assetPath.startsWith(MAJORITYIQ_PREFIX)) {
    assetPath =
      ASSEMBLYEDGE_PREFIX + assetPath.slice(MAJORITYIQ_PREFIX.length) || `${ASSEMBLYEDGE_PREFIX}/`;
  }
  const assetUrl = new URL(assetPath + incoming.search, incoming.origin);
  const assetRequest = new Request(assetUrl.toString(), c.req.raw);
  const assetResponse = await assets.fetch(assetRequest);
  if (assetResponse.status === 404) {
    return htmlBody(
      c,
      renderError({
        title: "Not found",
        message: "That MajorityIQ asset does not exist.",
        status: 404,
      }),
      404,
    );
  }

  const headers = new Headers(assetResponse.headers);
  applyAssemblyEdgeSecurityHeaders(headers, config.isProduction);
  return new Response(assetResponse.body, {
    status: assetResponse.status,
    headers,
  });
}

function requireDeskSession(c) {
  const session = c.get("session");
  if (!session.admin?.id) {
    return null;
  }
  return session;
}

function handleDeskApiCsrf(c) {
  const session = requireDeskSession(c);
  if (!session) {
    return c.json({ error: "unauthorized" }, 401);
  }
  const meta = askApiMeta(c.env, session);
  return c.json({
    csrfToken: c.get("csrfToken"),
    ...meta,
  });
}

async function handleDeskApiAsk(c) {
  const config = c.get("config");
  const sid = c.get("sid");
  let session = requireDeskSession(c);
  if (!session) {
    return c.json({ ok: false, error: "unauthorized" }, 401);
  }

  let body;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ ok: false, error: "bad_request", message: "Invalid JSON body." }, 400);
  }

  const csrfBody = typeof body._csrf === "string" ? body._csrf : "";
  if (
    !validateCsrfSubmission(
      c.req.raw,
      sid,
      config.sessionSecret,
      config.csrfCookieName,
      csrfBody,
    )
  ) {
    return c.json({ ok: false, error: "forbidden", message: "CSRF validation failed." }, 403);
  }

  const question = typeof body.question === "string" ? body.question.trim() : "";
  const mode = body.mode === "parse" ? "parse" : body.mode === "summarize" ? "summarize" : "assist";

  if (mode === "assist") {
    if (!question) {
      return c.json({ ok: false, error: "bad_request", message: "Missing question." }, 400);
    }
    const remaining = aiQuotaRemaining(session, c.env);
    if (remaining <= 0) {
      return c.json(
        {
          ok: false,
          error: "rate_limit",
          message: "Daily AI assist quota reached for this session. Deterministic answers still work in the browser.",
        },
        429,
      );
    }

    const parsed = await runAssemblyEdgeAskAi(c.env, "parse", { question });
    if (!parsed.ok) {
      return c.json({
        ok: false,
        error: parsed.error,
        message: parsed.message,
        aiNotice: parsed.message,
      });
    }

    session = bumpAiUsage(session);
    await setSession(c.env.DB, sid, session, config.sessionMaxAgeMs);

    return c.json({
      ok: true,
      query: parsed.query,
      aiRemaining: aiQuotaRemaining(session, c.env),
      aiNotice: "AI mapped your question; all figures are computed from static desk JSON in the browser.",
    });
  }

  if (mode === "summarize" || mode === "parse") {
    const remaining = aiQuotaRemaining(session, c.env);
    if (remaining <= 0) {
      return c.json(
        {
          ok: false,
          error: "rate_limit",
          message: "Daily AI assist quota reached for this session.",
        },
        429,
      );
    }
    const aiResult = await runAssemblyEdgeAskAi(c.env, mode, body);
    if (!aiResult.ok) {
      return c.json(aiResult, aiResult.error === "bad_request" ? 400 : 503);
    }
    session = bumpAiUsage(session);
    await setSession(c.env.DB, sid, session, config.sessionMaxAgeMs);
    return c.json({ ...aiResult, aiRemaining: aiQuotaRemaining(session, c.env) });
  }

  return c.json({ ok: false, error: "bad_request", message: "Unknown mode." }, 400);
}

for (const deskPrefix of [ASSEMBLYEDGE_PREFIX, MAJORITYIQ_PREFIX]) {
  app.get(`${deskPrefix}/api/csrf`, handleDeskApiCsrf);
  app.post(`${deskPrefix}/api/ask`, handleDeskApiAsk);
}

app.get(ASSEMBLYEDGE_PREFIX, (c) => c.redirect(`${ASSEMBLYEDGE_PREFIX}/`, 302));
app.get(`${ASSEMBLYEDGE_PREFIX}/*`, serveMajorityIQDesk);
app.get(MAJORITYIQ_PREFIX, (c) => c.redirect(`${MAJORITYIQ_PREFIX}/`, 302));
app.get(`${MAJORITYIQ_PREFIX}/*`, serveMajorityIQDesk);

app.post("/admin/logout", async (c) => {
  const config = c.get("config");
  const sid = c.get("sid");
  const session = c.get("session");
  const body = await c.req.parseBody();
  const csrfBody = typeof body._csrf === "string" ? body._csrf : "";

  if (!session.admin?.id) {
    return c.redirect("/admin/login", 302);
  }

  if (
    !validateCsrfSubmission(
      c.req.raw,
      sid,
      config.sessionSecret,
      config.csrfCookieName,
      csrfBody,
    )
  ) {
    return htmlBody(
      c,
      renderError({
        title: "Forbidden",
        message: "Your session expired or the request was invalid. Refresh and try again.",
        status: 403,
      }),
      403,
    );
  }

  await destroySession(c.env.DB, sid);
  deleteCookie(c, config.sessionCookieName, { path: "/" });
  deleteCookie(c, config.csrfCookieName, { path: "/" });
  return c.redirect("/admin/login", 302);
});

app.all("/admin/*", async (c) => {
  const session = c.get("session");
  const config = c.get("config");
  if (!session.admin?.id) {
    return c.redirect(`/admin/login?next=${encodeURIComponent(c.req.path)}`, 302);
  }
  return htmlBody(
    c,
    renderError({
      title: "Not found",
      message: "That admin page does not exist.",
      status: 404,
    }),
    404,
  );
});

app.onError((err, c) => {
  console.error(err);
  return htmlBody(
    c,
    renderError({
      title: "Error",
      message: "An unexpected error occurred.",
      status: 500,
    }),
    500,
  );
});

export default app;
