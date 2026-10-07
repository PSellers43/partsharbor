import fs from "node:fs";
import Database from "better-sqlite3";
import { getConfig } from "./config.js";

let db;

export function getDb() {
  if (db) return db;
  const { dataDir, dbPath } = getConfig();
  fs.mkdirSync(dataDir, { recursive: true });
  db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  migrate(db);
  return db;
}

function migrate(database) {
  database.exec(`
    CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE COLLATE NOCASE,
      password_hash TEXT NOT NULL,
      failed_attempts INTEGER NOT NULL DEFAULT 0,
      locked_until INTEGER,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      sid TEXT PRIMARY KEY,
      sess TEXT NOT NULL,
      expired INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS sessions_expired_idx ON sessions(expired);

    CREATE TABLE IF NOT EXISTS login_attempts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ip_hash TEXT NOT NULL,
      username_key TEXT NOT NULL,
      attempted_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS login_attempts_ip_idx ON login_attempts(ip_hash, attempted_at);
  `);
}

export function getAdminByUsername(username) {
  return getDb()
    .prepare(
      `SELECT id, username, password_hash, failed_attempts, locked_until
       FROM admins WHERE username = ? COLLATE NOCASE`,
    )
    .get(username);
}

export function countAdmins() {
  const row = getDb().prepare(`SELECT COUNT(*) AS n FROM admins`).get();
  return row.n;
}

export function insertAdmin(username, passwordHash) {
  const now = Date.now();
  getDb()
    .prepare(
      `INSERT INTO admins (username, password_hash, failed_attempts, locked_until, created_at, updated_at)
       VALUES (?, ?, 0, NULL, ?, ?)`,
    )
    .run(username, passwordHash, now, now);
}

export function recordFailedLogin(adminId) {
  const { login } = getConfig();
  const database = getDb();
  const admin = database
    .prepare(`SELECT failed_attempts FROM admins WHERE id = ?`)
    .get(adminId);
  const attempts = (admin?.failed_attempts ?? 0) + 1;
  let lockedUntil = null;
  if (attempts >= login.accountMaxFailures) {
    lockedUntil = Date.now() + login.accountLockMs;
  }
  database
    .prepare(
      `UPDATE admins SET failed_attempts = ?, locked_until = ?, updated_at = ?
       WHERE id = ?`,
    )
    .run(attempts, lockedUntil, Date.now(), adminId);
}

export function clearLoginFailures(adminId) {
  getDb()
    .prepare(
      `UPDATE admins SET failed_attempts = 0, locked_until = NULL, updated_at = ?
       WHERE id = ?`,
    )
    .run(Date.now(), adminId);
}

export function recordLoginAttempt(ipHash, usernameKey) {
  getDb()
    .prepare(
      `INSERT INTO login_attempts (ip_hash, username_key, attempted_at) VALUES (?, ?, ?)`,
    )
    .run(ipHash, usernameKey, Date.now());
}

export function countRecentLoginAttemptsByIp(ipHash, sinceMs) {
  const row = getDb()
    .prepare(
      `SELECT COUNT(*) AS n FROM login_attempts
       WHERE ip_hash = ? AND attempted_at >= ?`,
    )
    .get(ipHash, sinceMs);
  return row.n;
}

export function purgeOldLoginAttempts(olderThanMs) {
  getDb()
    .prepare(`DELETE FROM login_attempts WHERE attempted_at < ?`)
    .run(olderThanMs);
}
