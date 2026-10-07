import argon2 from "argon2";
import crypto from "node:crypto";
import { getConfig } from "./config.js";
import {
  clearLoginFailures,
  getAdminByUsername,
  recordFailedLogin,
  recordLoginAttempt,
  countRecentLoginAttemptsByIp,
  purgeOldLoginAttempts,
} from "./db.js";

/** Fixed dummy hash so verification timing is similar when username is unknown. */
let dummyHashPromise;

async function getDummyHash() {
  if (!dummyHashPromise) {
    dummyHashPromise = argon2.hash("partsharbor-timing-dummy", {
      type: argon2.argon2id,
      memoryCost: 19456,
      timeCost: 2,
      parallelism: 1,
    });
  }
  return dummyHashPromise;
}

export async function hashPassword(plain) {
  const { argon2: params } = getConfig();
  return argon2.hash(plain, {
    type: argon2.argon2id,
    memoryCost: params.memoryCost,
    timeCost: params.timeCost,
    parallelism: params.parallelism,
  });
}

export function hashClientIp(ip) {
  const { sessionSecret } = getConfig();
  return crypto.createHmac("sha256", sessionSecret).update(String(ip)).digest("hex");
}

export function normalizeUsername(input) {
  return String(input || "").trim().toLowerCase();
}

function usernameKey(username) {
  return crypto.createHash("sha256").update(username).digest("hex");
}

export function isAccountLocked(admin) {
  if (!admin?.locked_until) return false;
  return admin.locked_until > Date.now();
}

export async function verifyLogin(usernameInput, password, clientIp) {
  const { login } = getConfig();
  const username = normalizeUsername(usernameInput);
  const key = usernameKey(username || "empty");

  purgeOldLoginAttempts(Date.now() - login.ipWindowMs * 2);

  const ipHash = hashClientIp(clientIp);
  const ipAttempts = countRecentLoginAttemptsByIp(ipHash, Date.now() - login.ipWindowMs);
  if (ipAttempts >= login.ipMaxAttempts) {
    return { ok: false, reason: "rate_limited" };
  }

  recordLoginAttempt(ipHash, key);

  const admin = username ? getAdminByUsername(username) : null;
  const hashToVerify = admin?.password_hash ?? (await getDummyHash());

  let passwordOk = false;
  try {
    passwordOk = await argon2.verify(hashToVerify, password || "");
  } catch {
    passwordOk = false;
  }

  if (!admin || !passwordOk || isAccountLocked(admin)) {
    if (admin && !isAccountLocked(admin)) {
      recordFailedLogin(admin.id);
    }
    return { ok: false, reason: "invalid" };
  }

  clearLoginFailures(admin.id);
  return { ok: true, admin: { id: admin.id, username: admin.username } };
}
