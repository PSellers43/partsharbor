# Public polling refresh (MajorityIQ beachheads)

Curated **horse-race** public polls for tracked Assembly districts. MajorityIQ never invents poll numbers — only rows with a labeled source belong here.

## File

| Path | Purpose |
|------|---------|
| `latest.json` | Generated summary per beachhead (from `data/polls/released.json`) |
| `../polls/released.json` | Hand-verified public horse-race polls |
| `../polls/leads.json` | RSS leads to verify (no auto-toplines) |

## Refresh workflow (Patrick)

1. Add verified rows to `data/polls/released.json`, then run `./scripts/update-released-polls.sh` (or weekday `update-daily-majorityiq.sh`).
2. For each district, either:
   - **`poll`**: latest public horse-race survey with pollster, field dates, sample, margin (leader/trailer/undecided), MoE if published, and `source_url` + `source_label`.
   - **`gap`**: no qualifying public poll within `gap_recent_days` (default **90**). Gaps are first-class — do not delete the district row.
3. Optional **`history`**: older public polls (newest first) for sparklines; still cite sources.
4. Do **not** paste election-night results or forecast models as “polls.”
5. Campaign-commissioned surveys are allowed when disclosed; set `sponsor` and prefer independent/public pollsters when available.
6. Commit and deploy static assets; reload MajorityIQ — the **Polling & gaps** page picks up `latest.json` via `fetch` (no build step).

## UI behavior

- **Recent** poll (`field_end` within `gap_recent_days`): `chip-live` style, full infographic row.
- **Stale** poll (source exists but older than threshold): shown as “latest available” plus an explicit **gap** chip (“No public poll in last 90 days”).
- **No public poll on record**: gap-only row (no fabricated margin bars).

## Related

- Threat Index remains **demo/illustrative** until additional live feeds land (banner note).
- Money live totals: `data/calaccess/latest/money-by-district.json` (see `CALACCESS.md`).
