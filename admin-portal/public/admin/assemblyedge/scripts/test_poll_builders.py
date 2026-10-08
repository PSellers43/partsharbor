#!/usr/bin/env python3
"""Tests for poll lead merge + latest.json builder (no network)."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "polls" / "scripts"))

from fetch_poll_leads import lead_key, merge_leads  # noqa: E402
from poll_schema import is_recent_poll, pick_best_poll, sponsor_weight  # noqa: E402


def test_sponsor_weight():
    assert sponsor_weight("independent") == 1.0
    assert sponsor_weight("campaign") == 0.5
    assert sponsor_weight("party") == 0.5
    assert sponsor_weight("ie") == 0.5


def test_pick_best_recent():
    as_of = date(2026, 10, 8)
    polls = [
        {"district_id": "ad-7", "field_end": "2026-08-01", "pollster": "A"},
        {"district_id": "ad-7", "field_end": "2026-09-20", "pollster": "B"},
    ]
    best = pick_best_poll(polls, "ad-7", 90, as_of)
    assert best and best["pollster"] == "B"


def test_merge_leads_dedupes():
    existing = [{"title": "x", "link": "https://a.test/1", "date": "2026-10-01"}]
    new = [{"title": "x", "link": "https://a.test/1", "date": "2026-10-02", "fetched_at": "t2"}]
    merged = merge_leads(existing, new)
    assert len(merged) == 1
    assert merged[0]["last_seen"] == "t2"


def test_build_polling_latest_writes_gap_without_recent():
    script = ROOT / "data" / "polls" / "scripts" / "build_polling_latest.py"
    assert script.exists()
    import subprocess

    proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    latest = json.loads((ROOT / "data" / "polling" / "latest.json").read_text(encoding="utf-8"))
    ad7 = next(d for d in latest["districts"] if d["id"] == "ad-7")
    assert "poll" not in ad7 or ad7.get("poll") is None
    assert "No released poll" in ad7["gap"]["message"]


def main():
    for fn in [
        test_sponsor_weight,
        test_pick_best_recent,
        test_merge_leads_dedupes,
        test_build_polling_latest_writes_gap_without_recent,
    ]:
        fn()
        print("OK", fn.__name__)


if __name__ == "__main__":
    main()
