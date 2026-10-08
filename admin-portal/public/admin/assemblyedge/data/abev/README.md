# Ballot returns (ABEV-style) — beachhead Assembly districts

MajorityIQ step 3: vote-by-mail / ballot-return progress for **AD-7, 27, 36, 47, 58, 74** (CRC 2020 lines). Scoped to beachhead Assembly depth—not a statewide ballot-return clone.

## What ships in the UI

- **Portfolio** — six-district progress strip (live gap labeled; historical baselines shown).
- **Focus drill** — per-district panel beside demography.
- **Today's Board (CM)** — AD-7 pulse card + portfolio strip for field/ballot-chase context.

## Data files

| Path | Role |
|------|------|
| `latest/abev-by-district.json` | Browser fetch target |
| `latest/abev-by-district-YYYY-MM-DD.json` | Dated snapshot from refresh |

## Sources (free / public)

| Layer | Source | Notes |
|-------|--------|--------|
| Historical mail returns + party mix | [SWDB](https://statewidedatabase.org/) `All_VBM` by SR precinct | Voters who returned a mail ballot; aggregated to AD via `addist` on county SOV |
| Historical registration / turnout context | SWDB county SOV by SR precinct | `TOTREG`, `TOTVOTE` summed for beachhead `addist` rows |
| Current registration denominator | CA SOS ROR (via `data/demography/latest/demography-by-district.json`) | Odd-year Assembly worksheet—not the same snapshot as election SOV |
| Live 2026 returns | CA SOS [`bsr-statistics.xlsx`](https://elections.cdn.sos.ca.gov/statewide-elections/2026-general/bsr-statistics.xlsx) | **County-level only** — JSON lists intersecting counties per AD (not apportioned totals) |

### Limitations

- **No voter file, no PII** — precinct aggregates only.
- **Live 2026** — `live.status: county_level` when SOS workbook parses; otherwise explicit gap labels. No AD apportionment from county rows.
- **SOV registration** in baselines is the SWDB 15-day close-of-registration snapshot for that election, not today's ROR.
- **Party mix** on returns uses SWDB party codes (`DCL` → no party preference bucket).
- SOS daily VBM PDFs cannot be split to Assembly districts without county open-data or precinct joins (same approach as SWDB).

## Refresh

From `admin-portal/public/admin/assemblyedge`:

```bash
./scripts/update-abev.sh
# or daily cron companion:
./scripts/update-daily-majorityiq.sh
```

Or directly:

```bash
python3 data/abev/scripts/build_abev_json.py
```

Requires network access to `statewidedatabase.org` and optionally reads demography JSON locally. No API keys.

After refresh, commit updated `latest/*.json` and redeploy the admin Worker (static assets).

## When live feeds exist

1. Extend `build_abev_json.py` to ingest county/SOS CSV or API endpoints and populate each district's `live` block (`returned`, `as_of`, `party_returns`, `pct_of_registration`).
2. Re-run refresh and deploy—UI reads JSON only (no runtime third-party fetches in the browser).
