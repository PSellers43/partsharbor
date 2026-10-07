#!/usr/bin/env bash
# Smoke-test push-social-feed validation (no wrangler / no network).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="$ROOT/public/admin/assemblyedge/data/social/latest/social-feed.json"
if [[ ! -f "$SEED" ]]; then
  echo "Missing seed: $SEED" >&2
  exit 1
fi
"$ROOT/scripts/push-social-feed.sh" --dry-run "$SEED"
test -s /tmp/majorityiq-social-feed-push.sql
echo "OK push-social-feed dry-run · SQL written ($(wc -c < /tmp/majorityiq-social-feed-push.sql) bytes)"
