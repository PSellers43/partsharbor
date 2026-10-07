#!/usr/bin/env bash
# Refresh Focus drill demography + registration JSON (see data/demography/README.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 data/demography/scripts/build_demography_json.py "$@"
