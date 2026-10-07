/** Verify node `argon2` PHC hashes match `argon2id` wasm (bootstrap vs Worker). */
import argon2 from "argon2";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

// Load wasm manually for Node (mirrors worker bundle)
import setupWasm from "argon2id/lib/setup.js";
const wasmDir = join(__dirname, "../node_modules/argon2id/dist");
const simd = readFileSync(join(wasmDir, "simd.wasm"));
const noSimd = readFileSync(join(wasmDir, "no-simd.wasm"));

const instantiate = async (bytes, importObject) => {
  const result = await WebAssembly.instantiate(bytes, importObject);
  return { instance: result.instance };
};

const compute = await setupWasm(
  (io) => instantiate(simd, io),
  (io) => instantiate(noSimd, io),
);

const PARAMS = { memoryCost: 8192, timeCost: 2, parallelism: 1 };
const password = "TestAdminPass123!";
const phc = await argon2.hash(password, { type: argon2.argon2id, ...PARAMS });
console.log("phc", phc);

const [, , , paramStr, saltB64, hashB64] = phc.split("$");
const params = Object.fromEntries(paramStr.split(",").map((p) => p.split("=")));
const salt = Uint8Array.from(atob(saltB64), (c) => c.charCodeAt(0));
const expected = Uint8Array.from(atob(hashB64), (c) => c.charCodeAt(0));

const digest = compute({
  password: new TextEncoder().encode(password),
  salt,
  parallelism: Number(params.p),
  passes: Number(params.t),
  memorySize: Number(params.m),
  tagLength: expected.length,
});

const ok = digest.length === expected.length && digest.every((b, i) => b === expected[i]);
console.log("wasm matches node phc:", ok);
console.log("node verify:", await argon2.verify(phc, password));
