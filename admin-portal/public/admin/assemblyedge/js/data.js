/* MajorityIQ — static roster + empty intel placeholders until JSON bundles load. */

window.AE = window.AE || {};

AE.DEMO_BANNER =
  "Real public data, refreshed manually — each panel shows its as-of time (PT). Estimates are tagged EST. Synthetic/illustrative items are tagged DEMO. Not official FPPC/SOS/caucus figures.";

function aeDistrictSkeleton(row) {
  return {
    ...row,
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: "unavailable",
    lean: null,
    lean_meta: null,
    history_note: null,
  };
}

AE.districts = [
  aeDistrictSkeleton({
    id: "ad-7",
    code: "AD-7",
    name: "Hoover",
    incumbent: "Josh Hoover",
    party: "R",
    region: "Sacramento / Folsom",
    seatType: "Incumbent",
  }),
  aeDistrictSkeleton({
    id: "ad-47",
    code: "AD-47",
    name: "Wallis",
    incumbent: "Greg Wallis",
    party: "R",
    region: "Inland Empire",
    seatType: "Incumbent",
  }),
  aeDistrictSkeleton({
    id: "ad-58",
    code: "AD-58",
    name: "Castillo",
    incumbent: "Leticia Castillo",
    party: "R",
    region: "Riverside corridor",
    seatType: "Incumbent",
  }),
  aeDistrictSkeleton({
    id: "ad-74",
    code: "AD-74",
    name: "Davies",
    incumbent: "Laurie Davies",
    party: "R",
    region: "Orange / North San Diego",
    seatType: "Incumbent",
  }),
  aeDistrictSkeleton({
    id: "ad-36",
    code: "AD-36",
    name: "Gonzalez",
    incumbent: "Jeff Gonzalez",
    party: "R",
    region: "Imperial / East Riverside (Coachella Valley)",
    seatType: "Incumbent",
  }),
  aeDistrictSkeleton({
    id: "ad-27",
    code: "AD-27",
    name: "Murphy vs Pacheco",
    incumbent: "Open seat — Murphy (R) vs Pacheco (D)",
    party: "Open",
    region: "Fresno / Madera (Central Valley)",
    seatType: "Open seat",
  }),
];

AE.factors = {};
AE.money = {};
AE.ads = {};
AE.narrative = {};
AE.rival = {};
AE.alerts = {};
AE.brief = {};
AE.cmPriorities = {};

AE.methodology = {
  money: {
    title: "Money velocity",
    body: "7-day late contributions and bucket WoW in the FPPC 90-day window (CAL-ACCESS S497/S496), ranked across the six beachheads. Cycle Form 460 totals appear on the Money tab.",
  },
  ie: {
    title: "IE pressure",
    body: "7-day anti-R independent expenditure volume from late-money ingest (support/oppose classified by target candidate party). CAL-ACCESS matched committees — not FPPC advice.",
  },
  ads: {
    title: "Ad surge",
    body: "Excluded from Threat Index until wired in the Ads tab. Ad data: see Ads tab.",
  },
  narrative: {
    title: "Narrative heat",
    body: "score = min(100, 20 × headlines in the last 7 days) from Google News RSS at build time. Zero headlines → score 0.",
  },
  polls: {
    title: "Poll movement",
    body: "Included only when a hand-curated public horse-race poll in data/polling/latest.json is inside the gap window. Missing or stale polls are excluded from the composite (weights renormalized) — never invent survey results.",
  },
};

AE.statusMeta = {
  elevated: { label: "Elevated", class: "chip-elevated" },
  watch: { label: "Watch", class: "chip-watch" },
  stable: { label: "Stable", class: "chip-stable" },
  unavailable: { label: "Loading", class: "chip-gap" },
};

AE.formatMoney = function (n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  if (Math.abs(v) >= 1e6) return "$" + (v / 1e6).toFixed(1) + "M";
  if (Math.abs(v) >= 1e3) return "$" + Math.round(v / 1000) + "k";
  return "$" + Math.round(v);
};
