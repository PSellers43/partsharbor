#!/usr/bin/env bash
# Refresh SWDB precinct election history layers for AssemblyEdge Focus drill.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 data/election-history/scripts/build_election_history_precincts.py
