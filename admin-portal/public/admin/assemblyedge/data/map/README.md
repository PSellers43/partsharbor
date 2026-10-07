# Focus map — CRC Assembly boundaries

| File | Description |
|------|-------------|
| `ca-assembly-crc-2020.geojson` | All 80 ADs for statewide context + highlighted beachheads (AD-7, 27, 36, 47, 58, 74). ~85 KB committed. |
| `intra/ad-*.geojson` | Beachhead drill-down: cities/CDPs clipped to each AD (~200 KB total). See `intra/README.md`. |
| `scripts/build_focus_map_geojson.py` | Re-download and rebuild from official CA Open Data / CRC layer. |
| `scripts/build_intra_district_geojson.py` | Rebuild beachhead intra-district layers from Census places + SWDB g22. |

## Official source (Patrick / desk refresh)

| | URL |
|---|-----|
| CRC Final Maps | https://wedrawthelines.ca.gov/final-maps/ |
| CA Open Data dataset | https://data.ca.gov/dataset/california-state-assembly-districts-map-2020 |
| Official KML (CRC 2020 Assembly) | https://gis.data.ca.gov/api/download/v1/items/1d4e5c18f82848afb7dbb2ce277f4c7d/kml?layers=0 |
| Same layer GeoJSON | https://gis.data.ca.gov/api/download/v1/items/1d4e5c18f82848afb7dbb2ce277f4c7d/geojson?layers=0 |

**Last built:** 2026-10-07 (UTC) via `python3 data/map/scripts/build_focus_map_geojson.py`

## Conversion notes

- Geometries are the **California Citizens Redistricting Commission** 2020-cycle Assembly districts published through CA Open Data (equivalent to the official KML download above).
- The build script pulls GeoJSON from that endpoint (same geometries as KML), then **decimates vertices** for static hosting on Cloudflare Workers Free: non-beachhead districts use a lower point budget for dim context outlines; beachhead districts retain more detail so shapes stay recognizable.
- **Not** for legal boundary work — use CRC / SOS authoritative files for that.

## Regenerate

From `admin-portal/public/admin/assemblyedge/`:

```bash
python3 data/map/scripts/build_focus_map_geojson.py
```

Commit the updated `ca-assembly-crc-2020.geojson` and bump the “Last built” date in this README.
