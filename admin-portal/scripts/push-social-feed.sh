#!/usr/bin/env bash
# Upload a MajorityIQ X digest into D1 (no redeploy). Run from admin-portal/ with wrangler auth.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRY_RUN=0
FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      echo "Usage: $0 [--dry-run] path/to/social-feed.json" >&2
      echo "  --dry-run  Validate and write SQL to /tmp only; skip wrangler d1 execute." >&2
      exit 0
      ;;
    *)
      if [[ -n "$FILE" ]]; then
        echo "Unexpected argument: $1" >&2
        exit 1
      fi
      FILE="$1"
      shift
      ;;
  esac
done

if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "Usage: $0 [--dry-run] path/to/social-feed.json" >&2
  exit 1
fi

cd "$ROOT"
ENRICH="$ROOT/public/admin/assemblyedge/data/social/scripts/enrich_sentiment.py"
if [[ -f "$ENRICH" ]]; then
  cp "$FILE" /tmp/majorityiq-social-feed-in.json
  python3 "$ENRICH" /tmp/majorityiq-social-feed-in.json
  FILE=/tmp/majorityiq-social-feed-in.json
fi

python3 - "$FILE" <<'PY'
import json, sys, time
from pathlib import Path

path = Path(sys.argv[1])
raw = json.loads(path.read_text(encoding="utf-8"))
if raw.get("schema") != 1:
    raise SystemExit("schema must be 1")
as_of = str(raw.get("as_of") or "").strip()
if not as_of:
    raise SystemExit("missing as_of")
hist = raw.get("sentiment_history") or []
if isinstance(hist, list) and len(hist) > 120 * 6:
    dates = sorted({r.get("date") for r in hist if isinstance(r, dict) and r.get("date")})
    keep = set(dates[-120:])
    raw["sentiment_history"] = [r for r in hist if isinstance(r, dict) and r.get("date") in keep]
payload = json.dumps(raw, separators=(",", ":"), ensure_ascii=False)
byte_size = len(payload.encode("utf-8"))
if byte_size > 750_000:
    raise SystemExit(f"payload too large: {byte_size} bytes (max 750000)")
updated_at = int(time.time() * 1000)
escaped = payload.replace("'", "''")
as_of_esc = as_of.replace("'", "''")
sql = (
    "INSERT OR REPLACE INTO majorityiq_social_feed "
    f"(id, as_of, payload, updated_at, byte_size) VALUES "
    f"(1, '{as_of_esc}', '{escaped}', {updated_at}, {byte_size});"
)
out = Path("/tmp/majorityiq-social-feed-push.sql")
out.write_text(sql, encoding="utf-8")
print(f"Validated schema 1 · as_of={as_of} · {byte_size} bytes → {out}")
PY

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] Skipping wrangler d1 execute. SQL ready at /tmp/majorityiq-social-feed-push.sql"
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] applying to remote D1…"
npx wrangler d1 execute partsharbor-admin --remote --file=/tmp/majorityiq-social-feed-push.sql
echo "Done. Refresh MajorityIQ in the browser (session GET /admin/majorityiq/api/social-feed)."
