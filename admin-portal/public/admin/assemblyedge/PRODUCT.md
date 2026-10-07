# AssemblyEdge — Product vision (prototype)

## What “state of the art” means here

A **competitive-intelligence desk**, not a dashboard slide. Operators see *what moved*, *why it scores*, and *what decision type to consider* — with Bloomberg-like density and Linear/Vercel polish. Threat Index is an explainable composite (money velocity, IE pressure, ad surge, narrative heat, poll movement), not a black-box “win probability.” Decision chips are **guidance taxonomy** (spend / hold / message / field), never fake certainty.

Beachhead: **GOP Assembly incumbents + toss-up seats**, starting with districts like AD-7 (Hoover) as the deep war room.

Two operator roles share one desk:

- **Analyst** — portfolio + deep charts (Threat / Money / Ads / Narrative / Rival / Alerts).
- **Campaign Manager** — ops-first **Today's Board** (24–72h priorities, decision log, war-room checklist). Role persists in `localStorage`.

## Screen inventory (this prototype)

1. **Portfolio home** — card grid of tracked districts, TI + deltas + status chips  
2. **District detail** — Threat / Money / Ads / Narrative / Rival / Alerts  
3. **Monday Brief** — one-page printable weekly rollup (AD-7)  
4. **Methodology / Trust** — sources, cadence, disclaimers, doctrine attributions  
5. **Command palette** — ⌘K jump to districts, roles, and actions  
6. **Chrome** — DEMO banner, **Analyst | Campaign Manager** role switcher, theme toggle, loading skeleton  
7. **CM Today's Board** — AD-7 Threat Index summary, persuasion/turnout mode, priority queue, decision log, war-room checklist  

## Doctrine (short citations only — no long quotes)

| Cite | Principle (paraphrase) |
|------|------------------------|
| Issenberg, *The Victory Lab* | Measure what moves votes; prefer tested tactics over folklore. |
| Green & Gerber, *Get Out the Vote* | GOTV effectiveness varies by tactic; prioritize evidence-backed contact modes. |
| Obama 2012 analytics (public postmortems) | Real-time ops need reliable data loops — dashboards field can act on. |
| Romney ORCA failures (public postmortems) | Unreliable Election Day systems fail; BOE needs tested fallbacks and simple truth. |
| Standard CM rhythms | Morning huddle, burn-rate discipline, persuasion↔turnout switches, rapid response, ballot chase, oppo hygiene. |

### UI feature → principle map

| UI feature | Principle |
|------------|-----------|
| Threat Index summary on Today's Board | Obama-style actionable signal — what moved, not vanity charts |
| Priority actions tagged **message / money / field / rapid response** | Issenberg + CM craft — named decision types over folklore |
| Evidence chips on each priority | Trace guidance to doctrine cites (demo) |
| Decision log (Spend / Hold / Message shift / Field surge + after-action note) | Measure & record operator choices; Issenberg accountability |
| Persuasion ↔ Turnout mode switch | Standard CM rhythm — late-cycle mode change |
| Checklist: Ad Library | Daily intel sweep (ad surge awareness) |
| Checklist: CAL-ACCESS delta | Money/IE hygiene before burn-rate moves |
| Checklist: Earned media scan | Narrative / rapid-response readiness |
| Checklist: EV / ballot chase | Green & Gerber GOTV + ballot chase rhythm |
| Checklist: Opposition claim tracker | Oppo hygiene + rapid response bench |
| Checklist: Field capacity / burn-rate / morning huddle / ED BOE | Field-capacity constraint; ORCA lesson on ED fallbacks |

## What becomes real data next (official / public sources only)

| Signal | Production source |
|--------|-------------------|
| Money & IE | CAL-ACCESS filings, late contributions (`data/calaccess/` daily ZIP ingest → `latest/money-by-district.json`) |
| Digital ads | Meta Ad Library, Google Ads Transparency |
| Narrative | Sourced news URLs with outlet + timestamp |
| Polls | Only disclosed public or properly attributed ranges — never invented |

Ingest → normalize → factor scores → TI + alerts → Monday Brief / CM Board. Every figure retains provenance and “as-of” stamps.

## Explicitly out of MVP

- Pricing, packaging, waitlists, “request demo” funnels  
- Email / SMS / Slack outreach or CRM sends  
- Automated spend orders or “guaranteed win” predictions  
- Claiming FPPC, SOS, or caucus official status  
- Private constituent data, voter-file PII, or invented personal emails  
- Paid third-party poll APIs as a hard dependency for v1  

## Success for this prototype

Patrick can open `index.html`, switch **Campaign Manager**, see Today's Board for AD-7, log a decision, tick the war-room checklist, switch back to **Analyst** for deeper charts — and it feels like a premium ops product, not a deck.
