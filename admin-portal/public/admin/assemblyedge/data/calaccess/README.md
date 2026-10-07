# CAL-ACCESS ingest (AssemblyEdge)

Official California Secretary of State **daily raw ZIP** → district money JSON for the prototype Money panel.

## Official source (only)

| Item | URL |
|------|-----|
| Raw data page | https://www.sos.ca.gov/campaign-lobbying/helpful-resources/raw-data-campaign-finance-and-lobbying-activity |
| Daily ZIP | https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip |
| Field guides ZIP | https://campaignfinance.cdn.sos.ca.gov/calaccess-documentation.zip |

**Cadence:** SOS updates the extract **once per day**. This folder stores ZIPs by date (`raw/dbwebexport-YYYY-MM-DD.zip`).

## TSV tables used

| File | Role |
|------|------|
| `CVR_CAMPAIGN_DISCLOSURE_CD.TSV` | Cover pages: filer, candidate, `OFFICE_CD=ASM`, `DIST_NO`, Form 460/496/465, support/oppose |
| `SMRY_CD.TSV` | Form 460 summary lines — **line 5** = total contributions (period), **line 11** = total expenditures |
| `S496_CD.TSV` | Late independent expenditure amounts (Form 496 schedule) |
| `S497_CD.TSV` | Late contributions (extracted; reserved for future Money/alerts wiring) |
| `FILERNAME_CD.TSV` | Filer names (available for enrichment) |

**Not expanded (too large):** `RCPT_CD.TSV` (~3.8 GB), `EXPN_CD.TSV` (~3.1 GB). Period committee totals come from `SMRY_CD` instead of itemizing every receipt/expense.

## Layout

```
data/calaccess/
  beachheads.json          # AD-7/47/58/74/36/27 name + committee patterns
  README.md                # this file
  scripts/ingest_calaccess.py
  raw/                     # dated official ZIPs (large)
  extract/YYYY-MM-DD/      # selected TSVs
  latest/
    money-by-district.json           # consumed by the prototype
    money-by-district-YYYY-MM-DD.json
    match-report.json
```

## Run

```bash
# From prototype root (recommended daily wrapper):
./scripts/update-calaccess.sh

# Or directly:
python3 data/calaccess/scripts/ingest_calaccess.py
python3 data/calaccess/scripts/ingest_calaccess.py --skip-download   # reuse today's ZIP/extract
```

Requires ~2 GB free for the ZIP plus ~1 GB for extracted TSVs. Runtime is dominated by download + SMRY scan (~2–5 min typical).

## Matching method (limitations)

1. Filter covers: `OFFICE_CD=ASM` + beachhead `DIST_NO` + report/thru/elect year ≥ cycle−2.
2. Score candidate committees against `beachheads.json` name/committee patterns; prefer names containing the cycle year (e.g. `2026`).
3. Sum Form 460 SMRY period amounts (latest `AMEND_ID` per `FILING_ID`).
4. IE: join F496/F465 covers to `S496_CD` amounts; `SUP_OPP_CD` S/O → support/oppose.

Name matching is **imperfect** (aliases, misspellings, ballot-measure committees, redistricting). See root `CALACCESS.md`.

## Legal / attribution

Public SOS CAL-ACCESS data. **Not** an FPPC, Secretary of State, or caucus endorsement. AssemblyEdge does not provide legal advice.
