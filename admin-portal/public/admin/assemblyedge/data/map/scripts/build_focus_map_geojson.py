#!/usr/bin/env python3
"""Build lean Focus map GeoJSON from official CRC 2020 Assembly boundaries.

Official sources (verify before re-run):
  - https://wedrawthelines.ca.gov/final-maps/
  - https://data.ca.gov/dataset/california-state-assembly-districts-map-2020
  - KML: https://gis.data.ca.gov/api/download/v1/items/1d4e5c18f82848afb7dbb2ce277f4c7d/kml?layers=0
  - GeoJSON (same layer): .../geojson?layers=0

This script downloads GeoJSON from CA Open Data (identical CRC geometries to the KML).
Beachhead districts get higher vertex budgets than context districts.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ca-assembly-crc-2020.geojson"
OFFICIAL_GEOJSON = (
    "https://gis.data.ca.gov/api/download/v1/items/"
    "1d4e5c18f82848afb7dbb2ce277f4c7d/geojson?layers=0"
)
OFFICIAL_KML = (
    "https://gis.data.ca.gov/api/download/v1/items/"
    "1d4e5c18f82848afb7dbb2ce277f4c7d/kml?layers=0"
)

BEACHHEAD = {"7", "27", "36", "47", "58", "74"}
CONTEXT_MAX_PTS = 30
BEACHHEAD_MAX_PTS = 110


def simplify_ring(ring: list, max_pts: int) -> list:
    if not ring:
        return ring
    closed = ring[0] == ring[-1]
    core = ring[:-1] if closed and len(ring) > 1 else list(ring)
    if len(core) <= max_pts:
        out = [[round(x, 5), round(y, 5)] for x, y in core]
    else:
        step = max(1, len(core) // max_pts)
        out = [[round(core[i][0], 5), round(core[i][1], 5)] for i in range(0, len(core), step)]
    if closed and out and out[0] != out[-1]:
        out.append(out[0][:])
    return out


def simplify_geom(geom: dict, max_pts: int) -> dict:
    t = geom["type"]
    if t == "Polygon":
        return {"type": "Polygon", "coordinates": [simplify_ring(r, max_pts) for r in geom["coordinates"]]}
    if t == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [[simplify_ring(r, max_pts) for r in poly] for poly in geom["coordinates"]],
        }
    raise ValueError(f"Unsupported geometry type: {t}")


def main() -> int:
    print("Fetching official CRC Assembly GeoJSON …")
    with urllib.request.urlopen(OFFICIAL_GEOJSON, timeout=120) as resp:
        src = json.load(resp)

    features = []
    for feat in src.get("features", []):
        props = feat.get("properties") or {}
        dist = str(props.get("DISTRICT") or props.get("DISTRICT_N") or "").strip()
        if not dist.isdigit():
            continue
        is_beach = dist in BEACHHEAD
        max_pts = BEACHHEAD_MAX_PTS if is_beach else CONTEXT_MAX_PTS
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "dist_no": dist,
                    "code": f"AD-{dist}",
                    "id": f"ad-{dist}" if is_beach else None,
                    "beachhead": is_beach,
                    "name": props.get("NAME") or props.get("DISTRICT_L") or "",
                },
                "geometry": simplify_geom(feat["geometry"], max_pts),
            }
        )

    if len(features) != 80:
        print(f"Warning: expected 80 districts, got {len(features)}", file=sys.stderr)

    out = {
        "type": "FeatureCollection",
        "source": {
            "authority": "California Citizens Redistricting Commission (2020 cycle)",
            "wedrawthelines": "https://wedrawthelines.ca.gov/final-maps/",
            "dataset": "https://data.ca.gov/dataset/california-state-assembly-districts-map-2020",
            "download_kml": OFFICIAL_KML,
            "download_geojson": OFFICIAL_GEOJSON,
            "fetched_at": date.today().isoformat(),
            "conversion_notes": (
                "Geometries from CA Open Data export of CRC Final Maps (same layer as official KML). "
                f"Vertex decimation: context ≤{CONTEXT_MAX_PTS} pts/ring, beachheads ≤{BEACHHEAD_MAX_PTS}. "
                "Not for legal boundary determinations."
            ),
        },
        "features": sorted(features, key=lambda f: int(f["properties"]["dist_no"])),
    }

    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(features)} features)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
