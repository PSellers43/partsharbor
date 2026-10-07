import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const portalRoot = path.join(__dirname, "..");

function requireEnv(name) {
  const value = process.env[name];
  if (!value || !value.trim()) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value.trim();
}

function loadConfig() {
  const nodeEnv = process.env.NODE_ENV === "production" ? "production" : "development";
  const isProduction = nodeEnv === "production";

  let sessionSecret;
  if (isProduction) {
    sessionSecret = requireEnv("SESSION_SECRET");
  } else {
    sessionSecret = process.env.SESSION_SECRET?.trim() || "dev-only-insecure-change-me-before-production";
  }

  if (sessionSecret.length < 32) {
    throw new Error("SESSION_SECRET must be at least 32 characters");
  }

  const dataDir = path.resolve(
    portalRoot,
    process.env.ADMIN_DATA_DIR?.trim() || "data",
  );
  const dbPath = path.join(dataDir, "admin-portal.db");

  const trustProxy =
    process.env.TRUST_PROXY === "1" ||
    process.env.TRUST_PROXY === "true" ||
    isProduction;

  const sessionMaxAgeSec = Number.parseInt(process.env.SESSION_MAX_AGE_SEC || "28800", 10);
  const sessionMaxAgeMs =
    Number.isFinite(sessionMaxAgeSec) && sessionMaxAgeSec > 0
      ? sessionMaxAgeSec * 1000
      : 8 * 60 * 60 * 1000;

  return {
    nodeEnv,
    isProduction,
    host: process.env.HOST?.trim() || "127.0.0.1",
    port: Number.parseInt(process.env.PORT || "8787", 10) || 8787,
    trustProxy,
    sessionSecret,
    sessionMaxAgeMs,
    dataDir,
    dbPath,
    adminUsername: process.env.ADMIN_USERNAME?.trim() || "admin",
    /** Argon2id params (OWASP-ish defaults for interactive login) */
    argon2: {
      type: 2, // argon2id — set at hash time in auth module
      memoryCost: 19456,
      timeCost: 2,
      parallelism: 1,
    },
    login: {
      ipWindowMs: 15 * 60 * 1000,
      ipMaxAttempts: 20,
      accountMaxFailures: 5,
      accountLockMs: 30 * 60 * 1000,
    },
    // __Host- prefix requires Secure + Path=/ (production only). Local HTTP uses plain names.
    csrfCookieName: isProduction ? "__Host-ph.csrf" : "ph.csrf",
    sessionCookieName: isProduction ? "__Host-ph.sid" : "ph.sid",
  };
}

/** Lazy singleton so bootstrap script can set env before import side effects. */
let cached;
export function getConfig() {
  if (!cached) cached = loadConfig();
  return cached;
}

export function resetConfigForTests() {
  cached = undefined;
}

export function randomToken(bytes = 32) {
  return crypto.randomBytes(bytes).toString("base64url");
}
