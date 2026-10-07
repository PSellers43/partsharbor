/**
 * Argon2id via `argon2id` (OpenPGP.js Wasm build). Same PHC format as the Node `argon2`
 * package used by scripts/bootstrap-admin.js (see scripts/cross-verify-argon.mjs).
 *
 * Workers Free: 10 ms CPU/request — see ADMIN.md for limits and parameter guidance.
 */
import setupWasm from "argon2id/lib/setup.js";
import wasmSIMD from "argon2id/dist/simd.wasm";
import wasmNonSIMD from "argon2id/dist/no-simd.wasm";

/** @type {import('argon2id/lib/setup.js').computeHash | null} */
let computeHash = null;

async function instantiateWasm(wasmImport, importObject) {
  if (typeof wasmImport === "function") {
    return wasmImport(importObject);
  }
  if (wasmImport instanceof WebAssembly.Module) {
    return { instance: new WebAssembly.Instance(wasmImport, importObject) };
  }
  const result = await WebAssembly.instantiate(wasmImport, importObject);
  return { instance: result.instance };
}

async function getCompute() {
  if (!computeHash) {
    computeHash = await setupWasm(
      (importObject) => instantiateWasm(wasmSIMD, importObject),
      (importObject) => instantiateWasm(wasmNonSIMD, importObject),
    );
  }
  return computeHash;
}

function b64NoPad(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/=+$/, "");
}

function b64Decode(str) {
  const padded = str + "=".repeat((4 - (str.length % 4)) % 4);
  const binary = atob(padded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

function parsePhc(phc) {
  const parts = phc.split("$");
  if (parts.length !== 6 || parts[1] !== "argon2id") {
    throw new Error("Unsupported password hash format");
  }
  const version = parts[2];
  if (version !== "v=19") throw new Error("Unsupported argon2 version");
  const paramMap = Object.fromEntries(parts[3].split(",").map((p) => p.split("=")));
  return {
    memoryKiB: Number.parseInt(paramMap.m, 10),
    parallelism: Number.parseInt(paramMap.p, 10),
    passes: Number.parseInt(paramMap.t, 10),
    salt: b64Decode(parts[4]),
    digest: b64Decode(parts[5]),
  };
}

function encodePhc({ memoryKiB, passes, parallelism, salt, digest }) {
  return [
    "",
    "argon2id",
    "v=19",
    `m=${memoryKiB},t=${passes},p=${parallelism}`,
    b64NoPad(salt),
    b64NoPad(digest),
  ].join("$");
}

/**
 * @param {string} plain
 * @param {{ memoryKiB: number, passes: number, parallelism: number, tagLength: number }} params
 */
export async function hashPassword(plain, params) {
  const argon2 = await getCompute();
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const digest = argon2({
    password: new TextEncoder().encode(plain),
    salt,
    parallelism: params.parallelism,
    passes: params.passes,
    memorySize: params.memoryKiB,
    tagLength: params.tagLength,
  });
  return encodePhc({
    memoryKiB: params.memoryKiB,
    passes: params.passes,
    parallelism: params.parallelism,
    salt,
    digest,
  });
}

/** @param {string} plain @param {string} phc */
export async function verifyPassword(plain, phc) {
  const parsed = parsePhc(phc);
  const argon2 = await getCompute();
  const digest = argon2({
    password: new TextEncoder().encode(plain || ""),
    salt: parsed.salt,
    parallelism: parsed.parallelism,
    passes: parsed.passes,
    memorySize: parsed.memoryKiB,
    tagLength: parsed.digest.length,
  });
  if (digest.length !== parsed.digest.length) return false;
  return timingSafeEqual(digest, parsed.digest);
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
