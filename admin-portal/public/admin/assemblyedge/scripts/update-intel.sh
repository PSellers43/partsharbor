#!/usr/bin/env bash
# Threat Index, news, rival, alerts — run after CAL-ACCESS ingest (weekday job).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] update-intel starting"
python3 data/threat-index/scripts/build_threat_index.py "$@"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] done → data/threat-index/latest/threat-index-by-district.json"
