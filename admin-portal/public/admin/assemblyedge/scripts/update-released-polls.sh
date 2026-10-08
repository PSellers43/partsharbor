#!/usr/bin/env bash
# Fetch poll leads (RSS only), rebuild latest.json from released.json — no auto-toplines.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] update-released-polls starting"
python3 data/polls/scripts/fetch_poll_leads.py
python3 data/polls/scripts/build_polling_latest.py
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] done → data/polls/leads.json + data/polling/latest.json"
