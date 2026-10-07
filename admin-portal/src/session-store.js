import { Store } from "express-session";
import { getDb } from "./db.js";

/**
 * SQLite-backed express-session store so logout and restart invalidate sessions predictably.
 */
export class SqliteSessionStore extends Store {
  constructor() {
    super();
    this.db = getDb();
    this.getStmt = this.db.prepare(`SELECT sess FROM sessions WHERE sid = ? AND expired > ?`);
    this.setStmt = this.db.prepare(
      `INSERT INTO sessions (sid, sess, expired) VALUES (?, ?, ?)
       ON CONFLICT(sid) DO UPDATE SET sess = excluded.sess, expired = excluded.expired`,
    );
    this.destroyStmt = this.db.prepare(`DELETE FROM sessions WHERE sid = ?`);
    this.touchStmt = this.db.prepare(`UPDATE sessions SET expired = ? WHERE sid = ?`);
  }

  get(sid, callback) {
    try {
      const row = this.getStmt.get(sid, Date.now());
      if (!row) return callback(null, null);
      callback(null, JSON.parse(row.sess));
    } catch (err) {
      callback(err);
    }
  }

  set(sid, session, callback) {
    try {
      const maxAge = session.cookie?.maxAge ?? 8 * 60 * 60 * 1000;
      const expired = Date.now() + maxAge;
      this.setStmt.run(sid, JSON.stringify(session), expired);
      callback(null);
    } catch (err) {
      callback(err);
    }
  }

  destroy(sid, callback) {
    try {
      this.destroyStmt.run(sid);
      callback(null);
    } catch (err) {
      callback(err);
    }
  }

  touch(sid, session, callback) {
    try {
      const maxAge = session.cookie?.maxAge ?? 8 * 60 * 60 * 1000;
      const expired = Date.now() + maxAge;
      this.touchStmt.run(expired, sid);
      callback(null);
    } catch (err) {
      callback(err);
    }
  }
}
