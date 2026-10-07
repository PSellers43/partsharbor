# MajorityIQ — Interactive Prototype

Premium war-room desk for **CA Assembly Republican competitive intelligence** (District Threat Index). Static HTML/CSS/JS — no build step, no paid APIs.

**All money, poll, and ad figures are DEMO / ILLUSTRATIVE.** Do not treat them as CAL-ACCESS or poll facts.

## Open it

```bash
# From this folder — any static server, or just open the file:
open index.html
# or
python3 -m http.server 8765
# then visit http://localhost:8765
```

Path: `/workspace/assemblyedge-prototype/index.html`

Desktop-first (1280+). Usable at 1280×800.


## Live CAL-ACCESS money (optional)

Official SOS daily ZIP ingest → `data/calaccess/latest/money-by-district.json`.

```bash
./scripts/update-calaccess.sh
python3 -m http.server 8765   # required so the Money tab can fetch JSON
```

Open **AD-7 → Money**: **LIVE CAL-ACCESS** badge + as-of time when JSON is present; otherwise clearly labeled demo. Details: `CALACCESS.md` and `data/calaccess/README.md`.

**Polling & gaps:** edit `data/polling/latest.json` (see `data/polling/README.md`). **Focus map:** CRC 2020 Assembly boundaries in `data/map/ca-assembly-crc-2020.geojson` (see `data/map/README.md` + rebuild script); score = 40% Threat Index + 35% money pressure + 25% polling gap severity (documented on map page).


## Flows to click (≈2 minutes) — Analyst

1. **Portfolio home** — six district cards (AD-7, 47, 58, 74, 36, 27) with Threat Index, 24h/7d deltas, Elevated / Watch / Stable chips.
2. **Open AD-7 (Hoover)** — deep demo. Tabs:
   - **Threat Index** — click any factor for methodology drawer
   - **Money** — candidate + IE receipts/spend, WoW deltas, sparklines
   - **Ads** — Meta + Google transparency-style cards (link-outs to real libraries)
   - **Narrative** — sourced headlines + sentiment tags
   - **Rival** — opponent + IE supporters/allies
   - **Alerts** — timeline with guidance chips (spend / hold / message)
3. **Monday Brief** — nav or button from AD-7 → printable one-pager → **Export PDF** (`window.print`)
4. **Methodology** — sources, cadence, disclaimers, CM doctrine attributions
5. **⌘K / Ctrl+K** — command palette to jump districts, roles, and actions
6. **Ask the desk** — **⌘/** or **Ask** in the nav (also on Today's Board): natural-language questions over loaded desk JSON (deterministic-first; optional Workers AI assist when deployed behind the admin Worker)
7. **Theme** — Light / Dark toggle (persists in `localStorage`)

Other districts show portfolio scores; full panels are wired for **AD-7** as the beachhead deep demo (empty states point you there).

## Campaign Manager flows to test

Role switcher lives in chrome: **Analyst | Campaign Manager** (persists as `ae-role` in `localStorage`).

1. Click **Campaign Manager** — primary view is **Today's Board** (AD-7 Threat Index summary + persuasion/turnout mode).
2. Scan **Priorities** (24h / 48h / 72h) — each card has action tags (`message` / `money` / `field` / `rapid response`) and **evidence** chips citing doctrine (demo).
3. **Quick-log** a decision — use Spend / Hold / Message shift / Field surge buttons on any priority; history appears under Decision log.
4. Or use the **Decision log form** — pick priority + decision + after-action note → Log decision. Clear log resets `ae-cm-decision-log`.
5. **War room checklist** — tick Ad Library, CAL-ACCESS delta, earned media, EV/ballot chase, opposition claim tracker (and related daily items). Checkboxes persist per calendar day in `ae-cm-checklist`.
6. Toggle **Persuasion / Turnout** mode (`ae-cm-race-mode`) — blurb updates.
7. Switch back to **Analyst** — portfolio / AD-7 desk / brief / methodology / ⌘K unchanged.
8. ⌘K → “Switch role → Campaign Manager” or “CM Board” also works.

## Files

| Path | Role |
|------|------|
| `index.html` | App shell + Analyst + CM screens |
| `css/styles.css` | Dark ops theme + light variant + CM board + print |
| `js/data.js` | Demo district / money / ads / narrative + CM priorities / doctrine |
| `js/cm.js` | Role, checklist, decision-log localStorage helpers |
| `js/app.js` | Navigation, tabs, palette, drawer, brief, CM board |
| `js/ask.js` | Ask the desk — intent parser + deterministic query executor |
| `PRODUCT.md` | Product vision + Doctrine map |

## Ask the desk (roadmap step 4)

Deterministic in-browser layer maps common question shapes to static JSON (CAL-ACCESS money, election-history precincts, demography/registration, ABEV baselines, polling, illustrative Threat Index). Answers include source labels, as-of stamps, small tables, and deep links into Focus drill / district tabs.

### Supported question patterns (examples)

| Pattern | Example |
|---------|---------|
| Precinct swing 2022→2024 | Which AD-7 precincts swung toward R between 2022 and 2024? |
| IE this week | How much IE money hit AD-58 this week? |
| Registration compare | Compare registration mix in AD-47 vs AD-74. |
| Mail / VBM returns | What were mail return rates in AD-36 in 2024? |
| Tight precincts in a city | Which Rancho Cordova precincts are within 2 points? |

Filters understood include beachhead `AD-N`, place/city names, `within N points`, `top N`, and IE + `this week` (latest 7-day bucket in CAL-ACCESS ingest series).

### Optional Workers AI (free tier only)

When MajorityIQ is served through the PartsHarbor admin Worker **and** `wrangler.toml` includes an `[ai]` binding:

- `POST /admin/majorityiq/api/ask` (and legacy `/admin/assemblyedge/api/ask`) with session auth + CSRF can parse ambiguous questions into the same JSON query schema the deterministic layer uses.
- Optional phrasing pass must not invent numbers — figures always come from client-side JSON.
- Default quota: **30 AI calls per session per UTC day** (`ASSEMBLYEDGE_ASK_AI_DAILY_LIMIT`), to stay within Cloudflare Workers AI free daily neurons.

**Disable AI** (deterministic-only, no Worker calls):

```toml
ASSEMBLYEDGE_ASK_AI = "false"
```

Or omit the `[ai]` binding — the UI falls back gracefully with a short notice.

**Deploy note:** after merging, run `wrangler deploy` from `admin-portal/` so the `[ai]` binding and `/admin/majorityiq/api/*` (plus legacy `/admin/assemblyedge/api/*`) routes are live. Static `python3 -m http.server` still runs Ask in deterministic mode (no CSRF/API).

`GET /admin/majorityiq/api/csrf` returns the CSRF token plus AI quota metadata for authenticated sessions (same handler on the legacy prefix).

**Free tier:** default **30 AI calls per session per UTC day** keeps usage within Cloudflare Workers AI’s free daily allocation. If the binding is missing, AI errors, or quota is exhausted, Ask keeps working in deterministic mode with a short notice — never a broken panel.

## Explicitly not in this prototype

- Emails, outreach CTAs, waitlists, pricing
- Inventing private contacts or mixing unlabeled demo with live filings
- Official FPPC / SOS / caucus branding
