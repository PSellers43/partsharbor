# Election history — precinct margins (AssemblyEdge Focus drill)

Static **SR precinct** GeoJSON for beachhead Assembly districts: real two-party **Assembly** margins from the UC Berkeley Statewide Database (SWDB), clipped to CRC 2020 AD boundaries. Consumed by the Focus intra-district drill **Election history** layer (`js/election-history.js`).

## Official sources

| Layer | Source | URL |
|-------|--------|-----|
| Precinct results (2022 & 2024 General) | SWDB SOV by SR precinct — `ASSDEM*` vs `ASSREP*` | [g22](https://statewidedatabase.org/d20/g22.html) · [g24](https://statewidedatabase.org/d20/g24.html) |
| Precinct boundaries | SWDB SR precinct shapefiles (`srprec_*_g22_v01_shp.zip`, g24 v01 fallback) | Same county folders under `/pub/data/G22/c###/` and `/pub/data/G24/c###/` |
| AD clip | CRC 2020 Assembly (`data/map/ca-assembly-crc-2020.geojson`) | [CRC maps](https://wedrawthelines.ca.gov/) |

**Not included:** voter file, modeled scores (e.g. Optiq-style), contact fields, or precinct registration.

## Layout

```
data/election-history/
  README.md
  scripts/build_election_history_precincts.py
  latest/
    election-history-index.json          # manifest (UI loader)
    election-history-index-YYYY-MM-DD.json
    ad-{7,27,36,47,58,74}-precincts.geojson
```

## Refresh

From the AssemblyEdge static root (`admin-portal/public/admin/assemblyedge/`):

```bash
python3 data/election-history/scripts/build_election_history_precincts.py
```

Or:

```bash
./scripts/update-election-history.sh
```

Requires Python 3, `shapely`, and `pyshp`; network access to SWDB and (for boundaries) cached assembly GeoJSON. Commit updated `latest/*` after verify. No Worker deploy secrets required.

## County coverage (beachheads)

| AD | Counties (FIPS) used in build |
|----|-------------------------------|
| 7 | Sacramento (067), Placer (061) |
| 27 | Fresno (019), Madera (039) |
| 36 | Imperial (025) — SOV `addist` filter (not Kern/LA) |
| 47, 58 | Riverside (065) |
| 74 | Orange (059) |

If SWDB omits a county SOV or shapes, the manifest records a row in `gaps[]` and the UI shows a labeled banner.

## Limitations

- **SR precinct** is the finest geography SWDB publishes statewide for free; precinct IDs can change between cycles — 2022 boundaries are drawn with g22 shapes, with g24 SOV joined on matching `srprec` within county.
- Two-party margin only (Dem + Rep); minor-party Assembly votes are excluded from the denominator.
- Small masked precincts in SWDB may show no contest totals.
- Static bundle size (~1.2 MB for six ADs) — extend beyond beachheads only with asset budget in mind.
