import { createHash, createHmac } from "node:crypto";
import {
  clearLoginFailures,
  countRecentLoginAttemptsByIp,
  getAdminByUsername,
  purgeOldLoginAttempts,
  recordFailedLogin,
  recordLoginAttempt,
} from "./db.js";
import { verifyPassword } from "./password.js";

/** Precomputed Argon2id PHC (m=8192,t=2,p=1) for timing-safe failed lookups. */
const DUMMY_PASSWORD_HASH =
  "$argon2id$v=19$m=8192,p=1,t=2$9JgfnzDgo2B6qgo/racdgQ$bhqq05kU53eEkm34szxn4hiRsUbXq8tAQDwzXY5Ys9w";

export function hashClientIp(ip, sessionSecret) {
  return createHmac("sha256", sessionSecret).update(String(ip)).digest("hex");
}

export function normalizeUsername(input) {
  return String(input || "").trim().toLowerCase();
}

function usernameKey(username) {
  return createHash("sha256").update(username).digest("hex");
}

export function isAccountLocked(admin) {
  if (!admin?.locked_until) return false;
  return Number(admin.locked_until) > Date.now();
}

/**
 * @param {import('@cloudflare/workers-types').D1Database} db
 */
export async function verifyLogin(db, config, usernameInput, password, clientIp) {
  const { login } = config;
  const username = normalizeUsername(usernameInput);
  const key = usernameKey(username || "empty");

  await purgeOldLoginAttempts(db, Date.now() - login.ipWindowMs * 2);

  const ipHash = hashClientIp(clientIp, config.sessionSecret);
  const ipAttempts = await countRecentLoginAttemptsByIp(
    db,
    ipHash,
    Date.now() - login.ipWindowMs,
  );
  if (ipAttempts >= login.ipMaxAttempts) {
    return { ok: false, reason: "rate_limited" };
  }

  await recordLoginAttempt(db, ipHash, key);

  const admin = username ? await getAdminByUsername(db, username) : null;
  const hashToVerify = admin?.password_hash ?? DUMMY_PASSWORD_HASH;

  let passwordOk = false;
  try {
    passwordOk = await verifyPassword(password || "", String(hashToVerify));
  } catch {
    passwordOk = false;
  }

  if (!admin || !passwordOk || isAccountLocked(admin)) {
    if (admin && !isAccountLocked(admin)) {
      await recordFailedLogin(db, admin.id, login.accountMaxFailures, login.accountLockMs);
    }
    return { ok: false, reason: "invalid" };
  }

  await clearLoginFailures(db, admin.id);
  return { ok: true, admin: { id: admin.id, username: admin.username } };
}
