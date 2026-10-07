/** @typedef {import('@cloudflare/workers-types').D1Database} D1Database */

/**
 * @typedef {Object} Env
 * @property {D1Database} DB
 * @property {Fetcher} [ASSETS]
 * @property {string} SESSION_SECRET
 * @property {string} [ENVIRONMENT]
 * @property {string} [ARGON2_MEMORY_KIB]
 * @property {string} [ARGON2_PASSES]
 * @property {string} [ARGON2_PARALLELISM]
 * @property {string} [SESSION_MAX_AGE_SEC]
 */

export function isProduction(env, url) {
  if (env.ENVIRONMENT === "production") return true;
  if (env.ENVIRONMENT === "development") return false;
  return url.protocol === "https:";
}

export function requireSessionSecret(env) {
  const secret = env.SESSION_SECRET?.trim();
  if (!secret || secret.length < 32) {
    throw new Error("SESSION_SECRET must be at least 32 characters");
  }
  return secret;
}

export function getConfig(env, url) {
  const production = isProduction(env, url);
  const sessionMaxAgeSec = Number.parseInt(env.SESSION_MAX_AGE_SEC || "28800", 10);
  const sessionMaxAgeMs =
    Number.isFinite(sessionMaxAgeSec) && sessionMaxAgeSec > 0
      ? sessionMaxAgeSec * 1000
      : 8 * 60 * 60 * 1000;

  return {
    isProduction: production,
    sessionSecret: requireSessionSecret(env),
    sessionMaxAgeMs,
    sessionCookieName: production ? "__Host-ph.sid" : "ph.sid",
    csrfCookieName: production ? "__Host-ph.csrf" : "ph.csrf",
    argon2: {
      memoryKiB: Number.parseInt(env.ARGON2_MEMORY_KIB || "8192", 10) || 8192,
      passes: Number.parseInt(env.ARGON2_PASSES || "2", 10) || 2,
      parallelism: Number.parseInt(env.ARGON2_PARALLELISM || "1", 10) || 1,
      tagLength: 32,
    },
    login: {
      ipWindowMs: 15 * 60 * 1000,
      ipMaxAttempts: 20,
      accountMaxFailures: 5,
      accountLockMs: 30 * 60 * 1000,
    },
  };
}
