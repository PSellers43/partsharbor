# Public polling refresh (MajorityIQ beachheads)

Curated **horse-race** public polls for tracked Assembly districts. MajorityIQ never invents poll numbers — only rows with a labeled source belong here.

## File

| Path | Purpose |
|------|---------|
| `latest.json` | One row per beachhead district (`ad-7`, `ad-47`, `ad-58`, `ad-74`, `ad-36`, `ad-27`) |

## Refresh workflow (Patrick)

1. Edit `latest.json` — bump `updated_at` (ISO-8601, UTC or with offset).
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
