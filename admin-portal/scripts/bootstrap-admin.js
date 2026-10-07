#!/usr/bin/env node
/**
 * Create the first admin in D1 (local or remote). Uses Node `argon2` (devDependency)
 * with the same PHC format the Worker verifies via Wasm `argon2id`.
 */
import { execSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import argon2 from "argon2";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const portalRoot = join(__dirname, "..");

const target = process.argv.includes("--remote") ? "remote" : "local";
const dbName = process.env.D1_DATABASE_NAME || "partsharbor-admin";

const ARGON2 = {
  memoryCost: Number.parseInt(process.env.ARGON2_MEMORY_KIB || "8192", 10),
  timeCost: Number.parseInt(process.env.ARGON2_PASSES || "2", 10),
  parallelism: Number.parseInt(process.env.ARGON2_PARALLELISM || "1", 10),
};

async function readPassword() {
  if (process.env.ADMIN_BOOTSTRAP_PASSWORD?.trim()) {
    return process.env.ADMIN_BOOTSTRAP_PASSWORD.trim();
  }
  const rl = readline.createInterface({ input, output });
  try {
    const first = await rl.question("New admin password (min 12 chars): ");
    const second = await rl.question("Confirm password: ");
    if (first !== second) throw new Error("Passwords did not match.");
    if (first.length < 12) throw new Error("Password must be at least 12 characters.");
    return first;
  } finally {
    rl.close();
  }
}

function sqlEscape(value) {
  return String(value).replace(/'/g, "''");
}

function runD1SqlFile(sql) {
  const flag = target === "remote" ? "--remote" : "--local";
  const dir = mkdtempSync(join(tmpdir(), "ph-bootstrap-"));
  const file = join(dir, "bootstrap.sql");
  writeFileSync(file, sql, "utf8");
  try {
    execSync(`npx wrangler d1 execute ${dbName} ${flag} --file=${file}`, {
      cwd: portalRoot,
      stdio: "inherit",
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

async function main() {
  const username = (process.env.ADMIN_USERNAME || "admin").trim().toLowerCase();
  if (!username) {
    console.error("Invalid ADMIN_USERNAME");
    process.exit(1);
  }

  const countRow = execSync(
    `npx wrangler d1 execute ${dbName} ${target === "remote" ? "--remote" : "--local"} --command "SELECT COUNT(*) AS n FROM admins" --json`,
    { cwd: portalRoot, encoding: "utf8" },
  );
  const parsed = JSON.parse(countRow);
  const n = Number(parsed?.[0]?.results?.[0]?.n ?? 0);
  if (n > 0) {
    console.error("An admin account already exists. Refusing to overwrite.");
    process.exit(1);
  }

  const password = await readPassword();
  const passwordHash = await argon2.hash(password, {
    type: argon2.argon2id,
    memoryCost: ARGON2.memoryCost,
    timeCost: ARGON2.timeCost,
    parallelism: ARGON2.parallelism,
  });

  const now = Date.now();
  const sql = `INSERT INTO admins (username, password_hash, failed_attempts, locked_until, created_at, updated_at) VALUES ('${sqlEscape(username)}', '${sqlEscape(passwordHash)}', 0, NULL, ${now}, ${now});\n`;
  runD1SqlFile(sql);
  console.log(`Created admin "${username}" in D1 (${target}).`);
  console.log("Set SESSION_SECRET: wrangler secret put SESSION_SECRET");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
