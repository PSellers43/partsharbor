#!/usr/bin/env python3
"""Sync data/polling/latest.json from verified released polls + beachhead roster."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLLS = ROOT / "data" / "polls"
POLLING = ROOT / "data" / "polling"
BEACH = ROOT / "data" / "calaccess" / "beachheads.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poll_schema import BEACHHEAD_IDS, is_recent_poll, legacy_poll_row, parse_date, pick_best_poll  # noqa: E402


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def race_label(beach: dict, did: str) -> str:
    for row in beach.get("districts") or []:
        if row.get("id") != did:
            continue
        if row.get("open_seat"):
            cands = row.get("general_candidates") or []
            if len(cands) >= 2:
                a, b = cands[0], cands[1]
                return (
                    f"Open seat · {a.get('name')} ({a.get('party', '?')}) vs "
                    f"{b.get('name')} ({b.get('party', '?')}) · Fresno corridor"
                )
            return "Open seat · AD-27"
        inc = row.get("incumbent") or {}
        opp = (row.get("known_opponents") or [{}])[0]
        if inc.get("name") and opp.get("name"):
            return (
                f"{inc.get('name')} ({inc.get('party', '?')}) incumbent vs "
                f"{opp.get('name')} ({opp.get('party', '?')})"
            )
    return did.upper()


def main() -> int:
    released_path = POLLS / "released.json"
    if not released_path.exists():
        print("Missing released.json", file=sys.stderr)
        return 1

    released = load_json(released_path)
    beach = load_json(BEACH) if BEACH.exists() else {"districts": []}
    gap_days = int(released.get("gap_recent_days") or 90)
    as_of = parse_date(released.get("updated_at")) or datetime.now(timezone.utc).date()
    polls = released.get("polls") or []

    districts_out = []
    for did in BEACHHEAD_IDS:
        code = "AD-" + did.split("-")[1]
        best = pick_best_poll(polls, did, gap_days, as_of)
        row: dict = {
            "id": did,
            "code": code,
            "race_label": race_label(beach, did),
        }
        district_polls = [p for p in polls if p.get("district_id") == did]
        district_polls.sort(key=lambda p: p.get("field_end") or "", reverse=True)
        if district_polls:
            row["released_poll_ids"] = [p.get("id") for p in district_polls if p.get("id")]

        if best:
            row["poll"] = legacy_poll_row(best)
        else:
            gap_msg = "No released poll in last 90 days"
            gap: dict = {"message": gap_msg, "as_of": as_of.isoformat()}
            if district_polls:
                stale = district_polls[0]
                end = stale.get("field_end")
                if end:
                    end_d = parse_date(end)
                    if end_d:
                        gap["days_since_field_end"] = (as_of - end_d).days
            row["gap"] = gap
        districts_out.append(row)

    payload = {
        "schema_version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "build_polling_latest.py",
        "gap_recent_days": gap_days,
        "released_path": "data/polls/released.json",
        "notes": released.get("notes") or "Horse-race polls only.",
        "districts": districts_out,
    }

    POLLING.mkdir(parents=True, exist_ok=True)
    out_path = POLLING / "latest.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(districts_out)} districts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
