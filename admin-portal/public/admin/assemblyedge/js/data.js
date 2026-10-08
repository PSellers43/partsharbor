/* MajorityIQ — static roster + operator UI defaults (no fictional TI/money/news). */

window.AE = window.AE || {};

AE.DEMO_BANNER =
  "Loading MajorityIQ bundles… Threat Index, news, rival, and alerts come from data/threat-index/latest/ after refresh. If a bundle fails, panels show Data unavailable — never placeholder scores.";

AE.districts = [
  {
    id: "ad-7",
    code: "AD-7",
    name: "Hoover",
    incumbent: "Josh Hoover",
    party: "R",
    region: "Sacramento / Folsom",
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: null,
    seatType: "Incumbent",
    lean: null,
  },
  {
    id: "ad-47",
    code: "AD-47",
    name: "Wallis",
    incumbent: "Greg Wallis",
    party: "R",
    region: "Inland Empire",
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: null,
    seatType: "Incumbent",
    lean: null,
  },
  {
    id: "ad-58",
    code: "AD-58",
    name: "Castillo",
    incumbent: "Leticia Castillo",
    party: "R",
    region: "Riverside corridor",
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: null,
    seatType: "Incumbent",
    lean: null,
  },
  {
    id: "ad-74",
    code: "AD-74",
    name: "Davies",
    incumbent: "Laurie Davies",
    party: "R",
    region: "Orange / North San Diego",
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: null,
    seatType: "Incumbent",
    lean: null,
  },
  {
    id: "ad-36",
    code: "AD-36",
    name: "Gonzalez",
    incumbent: "Jeff Gonzalez",
    party: "R",
    region: "Imperial / East Riverside (Coachella Valley)",
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: null,
    seatType: "Incumbent",
    lean: null,
  },
  {
    id: "ad-27",
    code: "AD-27",
    name: "Murphy vs Pacheco",
    incumbent: "Open seat — Murphy (R) vs Pacheco (D)",
    party: "Open",
    region: "Fresno / Madera (Central Valley)",
    threatIndex: null,
    delta24h: null,
    delta7d: null,
    status: null,
    seatType: "Open seat",
    lean: null,
  },
];

AE.factors = {};
AE.money = {};
AE.ads = {};
AE.narrative = {};
AE.rival = {};
AE.alerts = {};
AE.brief = {};

AE.methodology = {
  money: {
    title: "Money velocity",
    body: "7-day late contributions and bucket WoW in the FPPC 90-day window (CAL-ACCESS S497/S496), ranked across the six beachheads. Cycle Form 460 totals appear on the Money tab.",
  },
  ie: {
    title: "IE pressure",
    body: "7-day independent expenditure volume with direction-aware anti-R vs pro-R totals (target candidate party + support/oppose). CAL-ACCESS matched committees — not FPPC advice.",
  },
  ads: {
    title: "Ad surge",
    body: "Excluded from Threat Index until wired in this build. Ads tab shows availability state per district.",
  },
  narrative: {
    title: "Narrative heat",
    body: "score = min(100, 20 × headlines in the last 7 days) from Google News RSS at build time. Zero headlines → score 0.",
  },
  polls: {
    title: "Poll movement",
    body: "Included only when a hand-curated public horse-race poll in data/polling/latest.json is inside the gap window. Missing or stale polls are excluded from the composite (weights renormalized).",
  },
};

AE.statusMeta = {
  elevated: { label: "Elevated", class: "chip-elevated" },
  watch: { label: "Watch", class: "chip-watch" },
  stable: { label: "Stable", class: "chip-stable" },
  unavailable: { label: "Unavailable", class: "chip-gap" },
};

AE.formatMoney = function (n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  n = Number(n);
  if (n >= 1000) return "$" + Math.round(n / 1000) + "k";
  return "$" + n;
};

AE.doctrine = [
  { id: "issenberg", cite: "Issenberg, The Victory Lab", principle: "Measure what moves votes; prefer tested tactics over folklore." },
  { id: "green-gerber", cite: "Green & Gerber, Get Out the Vote", principle: "GOTV effectiveness varies by tactic; prioritize evidence-backed contact modes." },
  { id: "obama-2012", cite: "Obama 2012 analytics culture (public postmortems)", principle: "Real-time ops need reliable data loops — dashboards that field can act on." },
  { id: "orca", cite: "Romney ORCA postmortems (public)", principle: "Unreliable Election Day systems fail; BOE needs tested fallbacks and simple truth." },
  { id: "cm-craft", cite: "Standard CM craft", principle: "Morning huddle, burn-rate discipline, persuasion↔turnout switches, oppo hygiene, rapid response, ballot chase, ED BOE." },
  { id: "field-cap", cite: "Ground-war / field capacity literature", principle: "Field plans are constrained by volunteer/staff capacity — surge only what you can staff." },
];

AE.cmPriorities = [];

AE.cmActionMeta = {
  message: { label: "Message", class: "cm-act-message" },
  money: { label: "Money", class: "cm-act-money" },
  field: { label: "Field", class: "cm-act-field" },
  rapid: { label: "Rapid response", class: "cm-act-rapid" },
};

AE.cmDecisionTypes = [
  { id: "spend", label: "Spend" },
  { id: "hold", label: "Hold" },
  { id: "message", label: "Message shift" },
  { id: "field", label: "Field surge" },
];

AE.cmChecklist = [
  { id: "c-ads", label: "Ad Library sweep (Meta + Google)", group: "Intel" },
  { id: "c-cal", label: "CAL-ACCESS delta / late contributions", group: "Intel" },
  { id: "c-earned", label: "Earned media & narrative scan", group: "Intel" },
  { id: "c-oppo", label: "Opposition claim tracker updated", group: "Oppo hygiene" },
  { id: "c-rr", label: "Rapid response bench staffed today", group: "Oppo hygiene" },
  { id: "c-ev", label: "EV / ballot chase list pulled", group: "Turnout" },
  { id: "c-field", label: "Field capacity vs turf plan reconciled", group: "Turnout" },
  { id: "c-burn", label: "Paid burn-rate vs remaining weeks", group: "Money" },
  { id: "c-mode", label: "Persuasion vs turnout mode confirmed", group: "Strategy" },
  { id: "c-huddle", label: "Morning ops huddle held", group: "Ops" },
  { id: "c-boe", label: "ED BOE / coverage contingency reviewed", group: "Ops" },
];

AE.cmMode = {
  persuasion: {
    id: "persuasion",
    label: "Persuasion mode",
    blurb: "Undecideds still movable — message tests + targeted persuasion contacts ahead of pure turnout.",
  },
  turnout: {
    id: "turnout",
    label: "Turnout mode",
    blurb: "Bank ballot / GOTV — lean evidence-backed contact (Green & Gerber) within field capacity.",
  },
};
