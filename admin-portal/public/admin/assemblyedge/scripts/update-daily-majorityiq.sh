#!/usr/bin/env bash
# Daily MajorityIQ real-data refresh (no Worker redeploy). Pair with update-calaccess.sh on a weekday cron.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] update-daily-majorityiq starting"
./scripts/update-released-polls.sh
./scripts/update-abev.sh
python3 data/ads/scripts/build_ads_json.py --skip-download || python3 data/ads/scripts/build_ads_json.py
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] done → polls leads/latest + data/abev/latest/abev-by-district.json + data/ads/latest/ads-by-district.json (SOS BSR + SWDB baselines)"
