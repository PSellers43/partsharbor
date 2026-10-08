#!/usr/bin/env bash
# Cron-friendly daily CAL-ACCESS refresh for MajorityIQ.
# Example crontab (PT): 30 7 * * * /path/to/assemblyedge-prototype/scripts/update-calaccess.sh >> /var/log/calaccess-update.log 2>&1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] update-calaccess starting"
python3 data/calaccess/scripts/ingest_calaccess.py "$@"
bash scripts/update-intel.sh
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] done → data/calaccess/latest/money-by-district.json + late-money-by-district.json + threat-index"
