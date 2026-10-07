import path from "node:path";
import { fileURLToPath } from "node:url";
import cookieParser from "cookie-parser";
import express from "express";
import session from "express-session";
import rateLimit from "express-rate-limit";
import { doubleCsrf } from "csrf-csrf";
import { getConfig } from "./config.js";
import { countAdmins } from "./db.js";
import { verifyLogin } from "./auth.js";
import { SqliteSessionStore } from "./session-store.js";
import { buildHelmet, noCacheAdmin } from "./middleware/security.js";
import { requireAuth, redirectIfAuthed, safeNextPath } from "./middleware/require-auth.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const viewsDir = path.join(__dirname, "..", "views");
const staticDir = path.join(__dirname, "..", "public");

const config = getConfig();
const app = express();

if (config.trustProxy) {
  app.set("trust proxy", 1);
}

app.disable("x-powered-by");
app.use(buildHelmet());
app.use(noCacheAdmin);
app.use("/admin/static", express.static(staticDir, { maxAge: config.isProduction ? "1h" : 0 }));

app.use(
  express.urlencoded({
    extended: false,
    limit: "32kb",
  }),
);

app.use(cookieParser());

app.use(
  session({
    name: config.sessionCookieName,
    secret: config.sessionSecret,
    store: new SqliteSessionStore(),
    resave: false,
    saveUninitialized: false,
    rolling: true,
    cookie: {
      httpOnly: true,
      secure: config.isProduction,
      sameSite: "strict",
      maxAge: config.sessionMaxAgeMs,
      path: "/",
    },
  }),
);

/** CSRF tokens bind to session id; create a session before generating tokens. */
app.use((req, _res, next) => {
  if (!req.session.createdAt) {
    req.session.createdAt = Date.now();
  }
  next();
});

const {
  invalidCsrfTokenError,
  generateToken,
  doubleCsrfProtection,
} = doubleCsrf({
  getSecret: () => config.sessionSecret,
  cookieName: config.csrfCookieName,
  cookieOptions: {
    httpOnly: true,
    secure: config.isProduction,
    sameSite: "strict",
    path: "/",
  },
  getSessionIdentifier: (req) => req.sessionID || "",
  getTokenFromRequest: (req) => req.body?._csrf,
});

function csrfMiddleware(req, res, next) {
  doubleCsrfProtection(req, res, (err) => {
    if (
      err &&
      (err === invalidCsrfTokenError ||
        err.code === "EBADCSRFTOKEN" ||
        err.name === "ForbiddenError")
    ) {
      return res.status(403).render("error", {
        title: "Forbidden",
        message: "Your session expired or the request was invalid. Refresh and try again.",
        status: 403,
      });
    }
    if (err) return next(err);
    return next();
  });
}

app.use((req, res, next) => {
  try {
    // validateOnReuse=false: after session.regenerate(), rotate CSRF instead of throwing
    res.locals.csrfToken = generateToken(req, res, false, false);
  } catch (err) {
    return next(err);
  }
  res.locals.adminUser = req.session?.admin ?? null;
  next();
});

const loginLimiter = rateLimit({
  windowMs: config.login.ipWindowMs,
  max: config.login.ipMaxAttempts,
  standardHeaders: true,
  legacyHeaders: false,
  message: "Too many login attempts. Try again later.",
  handler(_req, res) {
    res.status(429).render("login", {
      title: "Admin sign in",
      error: "Too many login attempts. Try again later.",
      next: null,
    });
  },
});

app.set("view engine", "ejs");
app.set("views", viewsDir);

app.get("/healthz", (_req, res) => {
  res.type("text/plain").send("ok");
});

app.get("/", (_req, res) => {
  res.redirect("/admin");
});

app.get("/admin/login", redirectIfAuthed, (req, res) => {
  res.render("login", {
    title: "Admin sign in",
    error: null,
    next: safeNextPath(req.query.next),
  });
});

app.post("/admin/login", loginLimiter, csrfMiddleware, async (req, res) => {
  const username = req.body?.username;
  const password = req.body?.password;
  const clientIp = req.ip;

  if (countAdmins() === 0) {
    return res.status(503).render("login", {
      title: "Admin sign in",
      error: "Admin access is not configured yet. Run the bootstrap script on the server.",
      next: null,
    });
  }

  const result = await verifyLogin(username, password, clientIp);

  if (!result.ok) {
    const error =
      result.reason === "rate_limited"
        ? "Too many login attempts. Try again later."
        : "Invalid username or password.";
    return res.status(401).render("login", {
      title: "Admin sign in",
      error,
      next: safeNextPath(req.body?.next),
    });
  }

  await new Promise((resolve, reject) => {
    req.session.regenerate((err) => (err ? reject(err) : resolve()));
  });

  req.session.admin = {
    id: result.admin.id,
    username: result.admin.username,
  };

  generateToken(req, res, true, false);

  const destination = safeNextPath(req.body?.next) || "/admin";
  return res.redirect(destination);
});

app.get("/admin", requireAuth, (req, res) => {
  res.render("dashboard", {
    title: "Admin",
    sessionMeta: {
      username: req.session.admin.username,
      sessionId: maskSessionId(req.sessionID),
      expires: req.session.cookie?.expires ?? null,
    },
  });
});

app.post("/admin/logout", requireAuth, csrfMiddleware, (req, res) => {
  const sid = req.sessionID;
  req.session.destroy((err) => {
    if (err) {
      return res.status(500).render("error", {
        title: "Error",
        message: "Could not log out. Try again.",
        status: 500,
      });
    }
    res.clearCookie(config.sessionCookieName, {
      httpOnly: true,
      secure: config.isProduction,
      sameSite: "strict",
      path: "/",
    });
    res.clearCookie(config.csrfCookieName, {
      httpOnly: true,
      secure: config.isProduction,
      sameSite: "strict",
      path: "/",
    });
    if (sid) {
      // Store destroy is handled by session.destroy; extra clear for defense in depth
    }
    return res.redirect("/admin/login");
  });
});

app.use("/admin", requireAuth, (_req, res) => {
  res.status(404).render("error", {
    title: "Not found",
    message: "That admin page does not exist.",
    status: 404,
  });
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).render("error", {
    title: "Error",
    message: "An unexpected error occurred.",
    status: 500,
  });
});

function maskSessionId(sid) {
  if (!sid || sid.length < 8) return "—";
  return `${sid.slice(0, 4)}…${sid.slice(-4)}`;
}

app.listen(config.port, config.host, () => {
  console.log(
    `PartsHarbor admin portal listening on http://${config.host}:${config.port} (${config.nodeEnv})`,
  );
  if (countAdmins() === 0) {
    console.warn("No admin account in database — run: npm run bootstrap-admin");
  }
});
