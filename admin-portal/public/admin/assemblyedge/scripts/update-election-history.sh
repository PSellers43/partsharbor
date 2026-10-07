#!/usr/bin/env bash
# Refresh SWDB precinct election history layers for AssemblyEdge Focus drill.
# Downloads SWDB SOV + SR precinct shapes, Census TIGER places (city/CDP join), writes latest/*.geojson.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! python3 -c "import shapely, shapefile" 2>/dev/null; then
  echo "Install build deps: pip install shapely pyshp" >&2
  exit 1
fi
python3 data/election-history/scripts/build_election_history_precincts.py
