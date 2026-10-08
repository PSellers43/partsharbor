# CAL-ACCESS → MajorityIQ Money panel

## How to run

```bash
cd /workspace/assemblyedge-prototype
./scripts/update-calaccess.sh
# then serve the prototype so fetch() can load JSON:
python3 -m http.server 8765
# open http://localhost:8765 → AD-7 → Money
```

Idempotent: re-running the same day reuses `data/calaccess/raw/dbwebexport-YYYY-MM-DD.zip` unless you pass `--force-download`.

## What is real vs unmatched

| UI badge | Meaning |
|----------|---------|
| **LIVE CAL-ACCESS** | District has at least one strongly/moderately matched cycle committee with Form 460 SMRY totals from the official ZIP. |
| **CAL-ACCESS · weak match** | Some covers found but committee scoring was weak — treat cautiously. |
| **DEMO / ILLUSTRATIVE** | `money-by-district.json` missing, fetch failed (e.g. `file://` without a server), or no usable match — **demo `js/data.js` only**, never silently mixed with live figures. |

Each live row keeps provenance: `filer_id`, committee name, filing IDs, and SMRY/S496 source notes inside the JSON.

### AD-7 (Hoover deep) — example from a successful ingest

- Incumbent committee matched: **Hoover for Assembly 2026** (`filer_id` in JSON).
- Opponents matched when 2026 CTL committees exist (e.g. Slavensky, Taylor, Hoang).
- IE rows are Form 496 filers naming an ASM candidate in district 7.

Figures are **filed public totals**, not polls or caucus numbers. Period sums can include early-cycle activity on the same committee ID.

## Matching caveats

- **Name matching is imperfect.** Homonyms, spelling variants (“Lisa” vs “Porsche” Middleton), and committees that omit the district year can mis-score.
- **Ballot-measure / officeholder** committees for the same candidate are down-ranked but may still appear in raw CAL-ACCESS.
- **Redistricting:** `DIST_NO` on covers is what filers reported; historical AD-7 is not the same geography as today’s AD-7.
- **Opponent discovery** auto-adds other in-district `* for Assembly 2026` CTL committees not listed in `beachheads.json` (`match_quality: discovered`).
- **Candidate WoW** is `n/a` in the UI — Form 460 SMRY is period-based. IE WoW uses `S496` expenditure dates when present (noisy for sparse filers).
- **Weekly receipts** sparklines for candidates come from itemized `RCPT_CD` + `S497_CD` (Mon-week buckets via `build_weekly_receipts.py`). If insufficient rows, UI shows “not enough filings”. IE sparklines allocate spend across weeks with IE activity.

Edit patterns in `data/calaccess/beachheads.json` to improve matches; re-run the ingest (no re-download needed with `--skip-download`).

## Legal / attribution

- Data: **California Secretary of State**, Political Reform Division, CAL-ACCESS raw extract.
- Official page: https://www.sos.ca.gov/campaign-lobbying/helpful-resources/raw-data-campaign-finance-and-lobbying-activity
- Download: https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip
- MajorityIQ is **not** an official FPPC, SOS, or caucus product and does not provide legal or compliance advice.
- No voter-file PII is used. Contributor addresses from raw tables are not surfaced in the Money JSON.

## Disk / ops notes

- Daily ZIP is ~1.5 GB compressed; selected extracts ~1 GB.
- Cron: `scripts/update-calaccess.sh` (no Grok Bot routine unless separately requested).
- If download fails in an environment, the script exits non-zero and the UI stays on the demo badge — report the error honestly; do not invent numbers.
