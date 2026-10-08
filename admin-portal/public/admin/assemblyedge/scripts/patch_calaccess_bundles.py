#!/usr/bin/env python3
"""Patch committed CAL-ACCESS JSON when full re-ingest is unavailable."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ie_direction import classify_ie_row, excluded_target_names, roster_parties  # noqa: E402

BEACH = json.loads((ROOT / "data/calaccess/beachheads.json").read_text(encoding="utf-8"))
LATE_PATH = ROOT / "data/calaccess/latest/late-money-by-district.json"
MONEY_PATH = ROOT / "data/calaccess/latest/money-by-district.json"


def patch_late(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    beach_by_id = {d["id"]: d for d in BEACH.get("districts") or []}
    for did, row in (data.get("districts") or {}).items():
        beach = beach_by_id.get(did)
        money_dist = (json.loads(MONEY_PATH.read_text(encoding="utf-8")).get("districts") or {}).get(did) or {}
        roster = roster_parties(beach, money_dist)
        excluded = excluded_target_names(beach)
        ie_items = row.get("recent_ie") or []
        period_items = row.get("recent_contributions") or []
        t = row.setdefault("totals", {})
        ie_pro = ie_anti = 0.0
        for item in ie_items:
            effect = classify_ie_row(item.get("side") or "", item.get("target") or "", roster, excluded)
            if effect is None:
                continue
            amt = float(item.get("amount") or 0)
            if effect == "pro_r":
                ie_pro += amt
            else:
                ie_anti += amt
        t["ie_pro_r"] = round(ie_pro, 2)
        t["ie_anti_r"] = round(ie_anti, 2)
        dates = sorted(
            set(
                [i.get("contrib_date") for i in period_items if i.get("contrib_date")]
                + [i.get("exp_date") for i in ie_items if i.get("exp_date")]
            )
        )
        last_day = dates[-1] if dates else None
        t["last_filed_day_date"] = last_day
        t["last_filed_day"] = round(
            sum(float(i.get("amount") or 0) for i in period_items if i.get("contrib_date") == last_day),
            2,
        ) if last_day else 0.0
        t["ie_last_filed_day"] = round(
            sum(float(i.get("amount") or 0) for i in ie_items if i.get("exp_date") == last_day),
            2,
        ) if last_day else 0.0
        t["last_24h"] = t["last_filed_day"]
        t["ie_last_24h"] = t["ie_last_filed_day"]
    notes = data.setdefault("notes", [])
    note = "Last filed day totals use max contrib/exp date in export (not calendar 24h)."
    if note not in notes:
        notes.append(note)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {path}")


def patch_ie_sparklines(late: dict, money: dict) -> None:
    """Rebuild IE weekly $ series from late-money recent_ie lines."""
    for did, dist in (money.get("districts") or {}).items():
        late_row = (late.get("districts") or {}).get(did) or {}
        by_name: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
        for item in late_row.get("recent_ie") or []:
            key = (item.get("name") or "", item.get("side") or "")
            exp = item.get("exp_date")
            if not exp:
                continue
            by_name[key].append((exp, float(item.get("amount") or 0)))
        for ie in dist.get("ie") or []:
            key = (ie.get("name") or "", ie.get("side") or "")
            events = by_name.get(key)
            if not events:
                continue
            max_dt = max(datetime.fromisoformat(d) for d, _ in events)
            week_sums = [0.0] * 8
            for exp, amt in events:
                days_ago = (max_dt.date() - datetime.fromisoformat(exp).date()).days
                w = days_ago // 7
                if 0 <= w < 8:
                    week_sums[7 - w] += amt
            last, prev = week_sums[7], week_sums[6]
            if prev == 0 and last == 0:
                delta = 0.0
            elif prev == 0:
                delta = 100.0 if last > 0 else 0.0
            else:
                delta = round(100.0 * (last - prev) / prev, 1)
            ie["series"] = [round(x, 2) for x in week_sums]
            ie["deltaSpend"] = delta
            ie["series_note"] = "Weekly S496 expenditure dollars (8 buckets, newest last)"
            ie["deltaSpend_note"] = "WoW % from S496 dollar totals by week"
    MONEY_PATH.write_text(json.dumps(money, indent=2) + "\n", encoding="utf-8")
    print(f"Patched IE sparklines in {MONEY_PATH}")


def main() -> int:
    if not LATE_PATH.is_file():
        print("Missing late-money bundle", file=sys.stderr)
        return 1
    for p in LATE_PATH.parent.glob("late-money-by-district*.json"):
        patch_late(p)
    if MONEY_PATH.is_file():
        late = json.loads(LATE_PATH.read_text(encoding="utf-8"))
        money = json.loads(MONEY_PATH.read_text(encoding="utf-8"))
        patch_ie_sparklines(late, money)
        dated_money = MONEY_PATH.parent / "money-by-district-2026-10-07.json"
        if dated_money.is_file():
            m2 = json.loads(dated_money.read_text(encoding="utf-8"))
            patch_ie_sparklines(late, m2)
            dated_money.write_text(json.dumps(m2, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
