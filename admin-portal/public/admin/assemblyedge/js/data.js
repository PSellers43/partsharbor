/* MajorityIQ — DEMO / ILLUSTRATIVE DATA ONLY
   Not real CAL-ACCESS filings, polls, or ad library totals.
   Structure is plausible; figures are fictional for prototype UX. */

window.AE = window.AE || {};

AE.DEMO_BANNER = "MajorityIQ — Threat Index loads from data/threat-index/latest/ after refresh. Some layers still partial; not official FPPC, SOS, or caucus figures.";

AE.districts = [
  {
    id: "ad-7",
    code: "AD-7",
    name: "Hoover",
    incumbent: "Josh Hoover",
    party: "R",
    region: "Sacramento / Folsom",
    threatIndex: 72,
    delta24h: 4,
    delta7d: 11,
    status: "elevated",
    seatType: "Incumbent",
    lean: "R+3 (demo)",
  },
  {
    id: "ad-47",
    code: "AD-47",
    name: "Wallis",
    incumbent: "Greg Wallis",
    party: "R",
    region: "Inland Empire",
    threatIndex: 68,
    delta24h: 2,
    delta7d: 7,
    status: "elevated",
    seatType: "Incumbent",
    lean: "R+2 (demo)",
  },
  {
    id: "ad-58",
    code: "AD-58",
    name: "Castillo",
    incumbent: "Leticia Castillo",
    party: "R",
    region: "Riverside corridor",
    threatIndex: 61,
    delta24h: -1,
    delta7d: 3,
    status: "watch",
    seatType: "Incumbent",
    lean: "Even (demo)",
  },
  {
    id: "ad-74",
    code: "AD-74",
    name: "Davies",
    incumbent: "Laurie Davies",
    party: "R",
    region: "Orange / North San Diego",
    threatIndex: 54,
    delta24h: 0,
    delta7d: -2,
    status: "watch",
    seatType: "Incumbent",
    lean: "R+5 (demo)",
  },
  {
    id: "ad-36",
    code: "AD-36",
    name: "Gonzalez",
    incumbent: "Jeff Gonzalez",
    party: "R",
    region: "Imperial / East Riverside (Coachella Valley)",
    threatIndex: 41,
    delta24h: -2,
    delta7d: -5,
    status: "stable",
    seatType: "Incumbent",
    lean: "R+8 (demo)",
  },
  {
    id: "ad-27",
    code: "AD-27",
    name: "Murphy vs Pacheco",
    incumbent: "Open seat — Murphy (R) vs Pacheco (D)",
    party: "Open",
    region: "Fresno / Madera (Central Valley)",
    threatIndex: 38,
    delta24h: 1,
    delta7d: 0,
    status: "stable",
    seatType: "Open seat",
    lean: "D lean (demo)",
  },
];

AE.factors = {
  "ad-7": [
    { id: "money", label: "Money velocity", score: 78, weight: 0.25, trend: "up", blurb: "Opponent + IE cash paced above 8-week baseline." },
    { id: "ie", label: "IE pressure", score: 82, weight: 0.20, trend: "up", blurb: "Independent expenditure spend clustering in district ZIP cores." },
    { id: "ads", label: "Ad surge", score: 71, weight: 0.20, trend: "up", blurb: "Meta + Google creative volume up vs prior 14 days." },
    { id: "narrative", label: "Narrative heat", score: 65, weight: 0.20, trend: "flat", blurb: "Local outlets amplifying cost-of-living + crime frames." },
    { id: "polls", label: "Poll movement", score: 58, weight: 0.15, trend: "down", blurb: "Demo internal range tightened; not a public poll release." },
  ],
};

AE.methodology = {
  money: {
    title: "Money velocity",
    body: "7-day late contributions and bucket WoW in the FPPC 90-day window (CAL-ACCESS S497/S496), ranked across the six beachheads. Cycle Form 460 totals appear on the Money tab.",
  },
  ie: {
    title: "IE pressure",
    body: "7-day independent expenditure volume and oppose/support mix from late-money ingest. CAL-ACCESS matched committees — not FPPC advice.",
  },
  ads: {
    title: "Ad surge",
    body: "Excluded from Threat Index until a confirmed free Meta/Google feed covers CA Assembly advertisers. Ads tab shows an explicit unavailable state.",
  },
  narrative: {
    title: "Narrative heat",
    body: "score = min(100, 20 × headlines in the last 7 days) from Google News RSS at build time. Zero headlines → score 0.",
  },
  polls: {
    title: "Poll movement",
    body: "Uses the most recent verified horse-race poll in the 90-day window (released.json at build; private internal polls merged at runtime when logged in). Independent sponsors: full movement score. Campaign, party/caucus, or IE sponsors: same formula ×50% and a partisan-sponsor flag. No qualifying poll → factor excluded and other weights renormalized — never invent survey results.",
  },
};

AE.money = {
  "ad-7": {
    updated: "Demo snapshot · WoW illustrative",
    candidates: [
      { role: "Incumbent", name: "Josh Hoover", receipts: 185000, spend: 92000, deltaReceipts: 12, deltaSpend: 8, series: [40, 42, 45, 48, 52, 58, 62, 68] },
      { role: "Opponent", name: "Challenger (D)", receipts: 210000, spend: 145000, deltaReceipts: 18, deltaSpend: 22, series: [30, 35, 48, 55, 70, 88, 102, 120] },
    ],
    ie: [
      { name: "IE Coalition A (oppose R)", receipts: 320000, spend: 275000, deltaSpend: 31, side: "oppose", series: [20, 40, 80, 120, 160, 200, 240, 275] },
      { name: "IE Allies B (support R)", receipts: 95000, spend: 70000, deltaSpend: 5, side: "support", series: [10, 15, 22, 30, 40, 50, 60, 70] },
    ],
  },
};

AE.ads = {
  "ad-7": [
    { platform: "Meta", creatives: 24, spendBand: "$50k–$75k", firstSeen: "Sep 12", lastSeen: "Oct 5", sponsor: "IE Coalition A", link: "https://www.facebook.com/ads/library/", note: "Demo counts" },
    { platform: "Meta", creatives: 9, spendBand: "$10k–$25k", firstSeen: "Sep 28", lastSeen: "Oct 4", sponsor: "Hoover campaign (demo)", link: "https://www.facebook.com/ads/library/", note: "Demo counts" },
    { platform: "Google", creatives: 14, spendBand: "$25k–$50k", firstSeen: "Sep 18", lastSeen: "Oct 5", sponsor: "IE Coalition A", link: "https://adstransparency.google.com/", note: "Demo bands" },
    { platform: "Google", creatives: 6, spendBand: "$5k–$15k", firstSeen: "Oct 1", lastSeen: "Oct 5", sponsor: "IE Allies B", link: "https://adstransparency.google.com/", note: "Demo bands" },
  ],
};

AE.narrative = {
  "ad-7": [
    { outlet: "Sacramento Bee", title: "Assembly race heating as outside groups ramp spending", ts: "Oct 5 · 2:14p PT", sentiment: "neutral", url: "#" },
    { outlet: "CalMatters", title: "Suburban districts draw early IE attention ahead of November", ts: "Oct 4 · 9:02a PT", sentiment: "watch", url: "#" },
    { outlet: "Local Folsom Outlet", title: "Voters cite housing costs in door-knock feedback (anecdotal)", ts: "Oct 3 · 4:40p PT", sentiment: "negative", url: "#" },
    { outlet: "CAPITOL WEEKLY", title: "GOP incumbents watch money velocity in toss-up map", ts: "Oct 2 · 11:20a PT", sentiment: "neutral", url: "#" },
    { outlet: "KQED", title: "Ad libraries show uptick in digital buys around AD-7 ZIPs", ts: "Oct 1 · 3:55p PT", sentiment: "watch", url: "#" },
  ],
};

AE.rival = {
  "ad-7": {
    opponent: "Democratic challenger (demo label)",
    party: "D",
    notes: "Public race context only. Fundraising and IE alignment shown as illustrative structure.",
    ieSupporters: [
      { name: "IE Coalition A", role: "Oppose incumbent / support challenger", spendBand: "$250k–$300k demo" },
      { name: "Labor Partnership Demo", role: "Issue IE adjacent", spendBand: "$40k–$60k demo" },
    ],
    ieAllies: [
      { name: "IE Allies B", role: "Support incumbent", spendBand: "$60k–$80k demo" },
    ],
  },
};

AE.alerts = {
  "ad-7": [
    { ts: "Oct 5 · 6:10p PT", title: "IE spend band jumped WoW", detail: "Oppose-R IE spend +31% WoW (demo). Creative volume up on Meta.", decision: "spend", decisionLabel: "Consider spend" },
    { ts: "Oct 5 · 11:02a PT", title: "Narrative cluster: cost of living", detail: "Three local pieces in 48h on housing/utility frames.", decision: "message", decisionLabel: "Message check" },
    { ts: "Oct 4 · 4:22p PT", title: "Google Transparency: new creative set", detail: "14 creatives in $25–50k band (demo) attributed to IE Coalition A.", decision: "hold", decisionLabel: "Hold & monitor" },
    { ts: "Oct 3 · 9:15a PT", title: "Threat Index crossed Elevated", detail: "Composite moved 61 → 72 over 7 days (demo factors).", decision: "spend", decisionLabel: "Consider spend" },
    { ts: "Oct 1 · 2:00p PT", title: "Poll range tightened (demo internal)", detail: "Illustrative range only — not a public release.", decision: "hold", decisionLabel: "Hold & monitor" },
  ],
};

AE.brief = {
  "ad-7": {
    weekOf: "Week of Oct 6, 2026",
    headline: "AD-7 Elevated — IE velocity and ad surge drive Threat Index to 72",
    bullets: [
      "Threat Index 72 (+11 / 7d) — status Elevated. Primary drivers: IE pressure (82), money velocity (78).",
      "Opponent + oppose-R IE cash paced above 8-week baseline (demo). Meta creative count 24 in top oppose set.",
      "Narrative heat steady-high on cost-of-living; three local hits in 48h.",
      "Guidance chips (not certainty): Consider spend on digital counter; Message check on housing frame; Hold on TV until next IE filing window.",
    ],
    decisions: [
      { type: "spend", label: "Consider spend", note: "Match digital where IE creatives concentrate (demo ZIPs)." },
      { type: "message", label: "Message check", note: "Test cost-of-living response before weekend drop." },
      { type: "hold", label: "Hold & monitor", note: "Reassess after next CAL-ACCESS late-contribution cycle." },
    ],
  },
};

AE.statusMeta = {
  elevated: { label: "Elevated", class: "chip-elevated" },
  watch: { label: "Watch", class: "chip-watch" },
  stable: { label: "Stable", class: "chip-stable" },
};

AE.formatMoney = function (n) {
  if (n >= 1000) return "$" + Math.round(n / 1000) + "k";
  return "$" + n;
};

/* ——— Campaign Manager doctrine (short attributions; no copyrighted excerpts) ——— */
AE.doctrine = [
  { id: "issenberg", cite: "Issenberg, The Victory Lab", principle: "Measure what moves votes; prefer tested tactics over folklore." },
  { id: "green-gerber", cite: "Green & Gerber, Get Out the Vote", principle: "GOTV effectiveness varies by tactic; prioritize evidence-backed contact modes." },
  { id: "obama-2012", cite: "Obama 2012 analytics culture (public postmortems)", principle: "Real-time ops need reliable data loops — dashboards that field can act on." },
  { id: "orca", cite: "Romney ORCA postmortems (public)", principle: "Unreliable Election Day systems fail; BOE needs tested fallbacks and simple truth." },
  { id: "cm-craft", cite: "Standard CM craft", principle: "Morning huddle, burn-rate discipline, persuasion↔turnout switches, oppo hygiene, rapid response, ballot chase, ED BOE." },
  { id: "field-cap", cite: "Ground-war / field capacity literature", principle: "Field plans are constrained by volunteer/staff capacity — surge only what you can staff." },
];

AE.cmPriorities = [
  {
    id: "p1",
    horizon: "24h",
    title: "Counter IE digital in core ZIPs",
    detail: "Oppose-R IE Meta creatives up (demo). Match digital where creative volume concentrates — burn-rate check first.",
    actions: ["money", "message"],
    evidence: ["issenberg", "cm-craft"],
    alertId: "a0",
    urgency: "high",
  },
  {
    id: "p2",
    horizon: "24h",
    title: "Rapid response on cost-of-living frame",
    detail: "Three local hits in 48h. Prep one validated message variant; do not spray untested copy.",
    actions: ["message", "rapid"],
    evidence: ["issenberg", "cm-craft"],
    alertId: "a1",
    urgency: "high",
  },
  {
    id: "p3",
    horizon: "48h",
    title: "Early vote / ballot chase pulse",
    detail: "Demo EV window open. Chase outstanding ballots in high-propensity IDs before weekend drop.",
    actions: ["field"],
    evidence: ["green-gerber", "cm-craft"],
    alertId: null,
    urgency: "medium",
  },
  {
    id: "p4",
    horizon: "48h",
    title: "Field capacity gate before turf surge",
    detail: "Do not assign more doors than Saturday volunteer confirmations support.",
    actions: ["field"],
    evidence: ["field-cap", "green-gerber"],
    alertId: null,
    urgency: "medium",
  },
  {
    id: "p5",
    horizon: "72h",
    title: "CAL-ACCESS late-contribution watch",
    detail: "Hold major TV until next filing delta confirms IE trajectory (demo cadence).",
    actions: ["money"],
    evidence: ["cm-craft", "issenberg"],
    alertId: "a2",
    urgency: "low",
  },
  {
    id: "p6",
    horizon: "72h",
    title: "Election Day BOE dry-run note",
    detail: "Confirm poll-coverage fallbacks; avoid single-point digital BOE failure modes.",
    actions: ["field"],
    evidence: ["orca", "obama-2012"],
    alertId: null,
    urgency: "low",
  },
];

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
