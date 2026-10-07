#!/usr/bin/env node
/**
 * One-time (or rare) bootstrap: create the first admin user with Argon2id hash in SQLite.
 * Does not print or persist plaintext passwords in the repo.
 */
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { getConfig, resetConfigForTests } from "../src/config.js";
import { countAdmins, insertAdmin, getDb } from "../src/db.js";
import { hashPassword, normalizeUsername } from "../src/auth.js";

resetConfigForTests();

async function readPassword(prompt) {
  if (process.env.ADMIN_BOOTSTRAP_PASSWORD?.trim()) {
    return process.env.ADMIN_BOOTSTRAP_PASSWORD.trim();
  }
  const rl = readline.createInterface({ input, output });
  try {
    const first = await rl.question(`${prompt}: `);
    const second = await rl.question("Confirm password: ");
    if (first !== second) {
      throw new Error("Passwords did not match.");
    }
    if (first.length < 12) {
      throw new Error("Password must be at least 12 characters.");
    }
    return first;
  } finally {
    rl.close();
  }
}

async function main() {
  const config = getConfig();
  getDb();

  if (countAdmins() > 0) {
    console.error("An admin account already exists. Refusing to overwrite.");
    process.exit(1);
  }

  const username = normalizeUsername(process.env.ADMIN_USERNAME || config.adminUsername);
  if (!username) {
    console.error("Invalid ADMIN_USERNAME.");
    process.exit(1);
  }

  const password = await readPassword("New admin password (min 12 chars)");
  const passwordHash = await hashPassword(password);

  insertAdmin(username, passwordHash);
  console.log(`Created admin user "${username}" in ${config.dbPath}`);
  console.log("Store SESSION_SECRET in your secret manager before production deploy.");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
