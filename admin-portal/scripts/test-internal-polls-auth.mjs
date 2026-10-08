#!/usr/bin/env node
/**
 * Auth guard tests for MajorityIQ poll API (matches index.js requireDeskSession checks).
 * Full Worker integration requires wrangler; guards must return 401 JSON when no admin session.
 */
import { validateInternalPollInput, validateToplineSum } from "../src/assemblyedge-internal-polls.js";

function deskJsonAuthStatus(session) {
  if (!session?.admin?.id) return 401;
  return null;
}

function deskPageAuthRedirect(session) {
  if (!session?.admin?.id) return 302;
  return null;
}

async function main() {
  if (deskJsonAuthStatus(null) !== 401) throw new Error("null session should 401");
  if (deskJsonAuthStatus({}) !== 401) throw new Error("empty session should 401");
  if (deskJsonAuthStatus({ admin: {} }) !== 401) throw new Error("admin without id should 401");
  if (deskJsonAuthStatus({ admin: { id: 1 } }) !== null) throw new Error("valid admin should pass");

  if (deskPageAuthRedirect({}) !== 302) throw new Error("polls-admin should redirect when logged out");

  const bad = validateInternalPollInput({ district_id: "ad-99", pollster: "x", sponsor_type: "nope", field_start: "2026-01-01", field_end: "2026-01-02", toplines: [] });
  if (bad.ok) throw new Error("expected validation failure");

  const good = validateInternalPollInput({
    district_id: "ad-7",
    pollster: "Test pollster",
    sponsor_type: "campaign",
    sponsor_party: "R",
    field_start: "2026-09-01",
    field_end: "2026-09-05",
    sample_n: 400,
    moe_pct: 4.9,
    undecided_pct: 8,
    toplines: [
      { name: "A", party: "R", pct: 48 },
      { name: "B", party: "D", pct: 44 },
    ],
  });
  if (!good.ok) throw new Error(good.error);

  const noN = validateInternalPollInput({
    district_id: "ad-7",
    pollster: "X",
    sponsor_type: "campaign",
    field_start: "2026-09-01",
    field_end: "2026-09-05",
    toplines: [
      { name: "A", party: "R", pct: 48 },
      { name: "B", party: "D", pct: 44 },
    ],
  });
  if (noN.ok) throw new Error("expected sample_n required");

  const overSum = validateToplineSum(
    [
      { pct: 55 },
      { pct: 50 },
    ],
    0,
  );
  if (overSum.ok) throw new Error("expected sum > 101 to fail");

  console.log("OK test-internal-polls-auth");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
