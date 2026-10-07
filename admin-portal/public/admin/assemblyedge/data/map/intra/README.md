# Intra-district focus layers (beachheads)

Per–Assembly District GeoJSON for the Focus map **drill-down** view: Census **places** (cities + CDPs) clipped to the CRC 2020 AD boundary, colored by an illustrative **2022 g22** focus proxy.

| File | AD | Approx. size | Places |
|------|-----|-------------|--------|
| `ad-7.geojson` | Sacramento / Folsom | ~21 KB | 12 |
| `ad-27.geojson` | Central Valley | ~45 KB | 43 |
| `ad-36.geojson` | Antelope Valley | ~56 KB | 47 |
| `ad-47.geojson` | Inland Empire | ~48 KB | 30 |
| `ad-58.geojson` | Riverside corridor | ~16 KB | 9 |
| `ad-74.geojson` | Orange County | ~17 KB | 9 |

**Total committed:** ~200 KB (Workers Free static assets).

## Data provenance

| Layer | Source |
|-------|--------|
| Place boundaries | [Census cartographic places 2020 (500k)](https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_06_place_500k.zip) |
| AD clip | `../ca-assembly-crc-2020.geojson` (CRC 2020 Assembly) |
| 2022 votes | [SWDB g22 SOV by SR precinct](https://statewidedatabase.org/d20/g22.html) (per county CSV) |
| Place ↔ precinct | [SWDB `state_g22_srprec_to_city.csv`](https://statewidedatabase.org/pub/data/G22/state/state_g22_srprec_to_city.csv) |

## Focus score (UI + `source.score_formula`)

Illustrative **0–100** ops proxy (not field targeting):

- **70%** competitiveness from 2022 Assembly two-party margin in overlapping SR precincts (closer margin → higher score)
- **30%** turnout proxy (`TOTVOTE / TOTREG`) in those precincts

Votes are allocated to place names using SWDB `N_IN_CITY / N` weights. Unincorporated areas and places without g22 overlap may score 0 with `has_election_data: false`.

## Regenerate

From `admin-portal/public/admin/assemblyedge/` (requires `shapely`, `pyshp`; network for Census + SWDB):

```bash
python3 data/map/scripts/build_intra_district_geojson.py
```

Commit updated `ad-*.geojson` and bump dates in this README.

## Extending beyond beachheads

Add the district to `BEACHHEAD` / `COUNTY_FIPS` in `build_intra_district_geojson.py`, regenerate, and register the AD in `js/focus-drill.js` (`BEACHHEAD_IDS`). Statewide all-80 AD layers are intentionally **not** shipped to stay within free-tier asset limits.
