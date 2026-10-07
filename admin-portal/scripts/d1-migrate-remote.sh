#!/usr/bin/env bash
# Apply D1 migrations to remote. Falls back to per-file execute when migrations API fails (e.g. CF 7403).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DB="partsharbor-admin"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

set +e
npx wrangler d1 migrations apply "$DB" --remote 2>&1 | tee "$LOG"
STATUS=${PIPESTATUS[0]}
set -e

if [[ "$STATUS" -eq 0 ]]; then
  exit 0
fi

if grep -qiE '7403|10000|authentication error|not authorized|migrations' "$LOG"; then
  echo ""
  echo "wrangler d1 migrations apply --remote failed (often Cloudflare API error 7403)."
  echo "Falling back to per-file remote execute (idempotent SQL only):"
  for f in "$ROOT"/migrations/*.sql; do
    [[ -f "$f" ]] || continue
    echo "  → $(basename "$f")"
    npx wrangler d1 execute "$DB" --remote --file="$f"
  done
  echo "Done (fallback path)."
  exit 0
fi

echo "Migration failed; see output above." >&2
exit "$STATUS"
