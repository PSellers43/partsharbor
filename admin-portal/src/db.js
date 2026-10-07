/** @param {import('./config.js').Env} db @typedef from D1 - use env.DB */

export async function getAdminByUsername(db, username) {
  return db
    .prepare(
      `SELECT id, username, password_hash, failed_attempts, locked_until
       FROM admins WHERE username = ? COLLATE NOCASE`,
    )
    .bind(username)
    .first();
}

export async function countAdmins(db) {
  const row = await db.prepare(`SELECT COUNT(*) AS n FROM admins`).first();
  return Number(row?.n ?? 0);
}

export async function insertAdmin(db, username, passwordHash) {
  const now = Date.now();
  await db
    .prepare(
      `INSERT INTO admins (username, password_hash, failed_attempts, locked_until, created_at, updated_at)
       VALUES (?, ?, 0, NULL, ?, ?)`,
    )
    .bind(username, passwordHash, now, now)
    .run();
}

export async function recordFailedLogin(db, adminId, accountMaxFailures, accountLockMs) {
  const admin = await db
    .prepare(`SELECT failed_attempts FROM admins WHERE id = ?`)
    .bind(adminId)
    .first();
  const attempts = Number(admin?.failed_attempts ?? 0) + 1;
  let lockedUntil = null;
  if (attempts >= accountMaxFailures) {
    lockedUntil = Date.now() + accountLockMs;
  }
  await db
    .prepare(
      `UPDATE admins SET failed_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?`,
    )
    .bind(attempts, lockedUntil, Date.now(), adminId)
    .run();
}

export async function clearLoginFailures(db, adminId) {
  await db
    .prepare(
      `UPDATE admins SET failed_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?`,
    )
    .bind(Date.now(), adminId)
    .run();
}

export async function recordLoginAttempt(db, ipHash, usernameKey) {
  await db
    .prepare(
      `INSERT INTO login_attempts (ip_hash, username_key, attempted_at) VALUES (?, ?, ?)`,
    )
    .bind(ipHash, usernameKey, Date.now())
    .run();
}

export async function countRecentLoginAttemptsByIp(db, ipHash, sinceMs) {
  const row = await db
    .prepare(
      `SELECT COUNT(*) AS n FROM login_attempts WHERE ip_hash = ? AND attempted_at >= ?`,
    )
    .bind(ipHash, sinceMs)
    .first();
  return Number(row?.n ?? 0);
}

export async function purgeOldLoginAttempts(db, olderThanMs) {
  await db
    .prepare(`DELETE FROM login_attempts WHERE attempted_at < ?`)
    .bind(olderThanMs)
    .run();
}

export async function getSession(db, sid) {
  const row = await db
    .prepare(`SELECT sess FROM sessions WHERE sid = ? AND expired > ?`)
    .bind(sid, Date.now())
    .first();
  if (!row?.sess) return null;
  return JSON.parse(String(row.sess));
}

export async function setSession(db, sid, session, maxAgeMs) {
  const expired = Date.now() + maxAgeMs;
  await db
    .prepare(
      `INSERT INTO sessions (sid, sess, expired) VALUES (?, ?, ?)
       ON CONFLICT(sid) DO UPDATE SET sess = excluded.sess, expired = excluded.expired`,
    )
    .bind(sid, JSON.stringify(session), expired)
    .run();
}

export async function destroySession(db, sid) {
  await db.prepare(`DELETE FROM sessions WHERE sid = ?`).bind(sid).run();
}

export async function touchSession(db, sid, maxAgeMs) {
  const expired = Date.now() + maxAgeMs;
  await db
    .prepare(`UPDATE sessions SET expired = ? WHERE sid = ?`)
    .bind(expired, sid)
    .run();
}
