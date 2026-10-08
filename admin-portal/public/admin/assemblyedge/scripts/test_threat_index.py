#!/usr/bin/env python3
"""Unit tests for Threat Index computation."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "threat-index" / "scripts"))

from ti_compute import (  # noqa: E402
    WEIGHTS,
    composite_ti,
    compute_district_ti,
    ie_pressure_raw,
    money_velocity_raw,
    normalize_across,
    poll_is_recent,
    poll_movement_raw,
    status_from_ti,
)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_status_thresholds():
    assert status_from_ti(65) == "elevated"
    assert status_from_ti(64) == "watch"
    assert status_from_ti(45) == "watch"
    assert status_from_ti(44) == "stable"


def test_composite_ti_weighted():
    scores = {"money": 80, "ie": 60, "narrative": 40, "polls": 50}
    ti = composite_ti(scores)
    expected = sum(WEIGHTS[k] * scores[k] for k in WEIGHTS)
    assert ti == round(expected)


def test_normalize_spreads_values():
    raw = {"ad-7": 1.0, "ad-74": 5.0}
    out = normalize_across(raw)
    assert out["ad-7"] < out["ad-74"]


def test_poll_stale_caps_score():
    as_of = dt.date(2026, 10, 7)
    row = {
        "poll": {
            "pollster": "Test",
            "field_end": "2022-01-01",
            "margin": {"leader_party": "D", "leader_pct": 50, "trailer_pct": 45},
        }
    }
    score, blurb = poll_movement_raw(row, 90, as_of)
    assert score <= 48
    assert "Stale" in blurb


def test_bundle_json_valid():
    path = ROOT / "data" / "threat-index" / "latest" / "threat-index-by-district.json"
    assert path.exists(), "Run build_threat_index.py first"
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"]
    for did in ids:
        row = data["districts"][did]
        assert 0 <= row["threatIndex"] <= 100
        assert row["status"] in ("elevated", "watch", "stable")
        assert len(row["factors"]) == 5
        ads = next(f for f in row["factors"] if f["id"] == "ads")
        assert ads.get("unavailable") is True
        assert data["narrative"][did]
        assert data["rival"][did]["opponent"]
        assert data["alerts"][did]


def test_late_money_inputs_change_ti():
    as_of = dt.date(2026, 10, 8)
    late_high = {"totals": {"seven_day": 500000, "ie_seven_day": 400000, "ie_oppose": 200000, "ie_support": 50000}, "daily_buckets": [{"amount": 100}] * 20}
    late_low = {"totals": {"seven_day": 1000, "ie_seven_day": 500, "ie_oppose": 200, "ie_support": 100}, "daily_buckets": [{"amount": 10}] * 20}
    assert money_velocity_raw(late_high) > money_velocity_raw(late_low)
    assert ie_pressure_raw(late_high) > ie_pressure_raw(late_low)


def main():
    tests = [
        test_weights_sum_to_one,
        test_status_thresholds,
        test_composite_ti_weighted,
        test_normalize_spreads_values,
        test_poll_stale_caps_score,
        test_late_money_inputs_change_ti,
        test_bundle_json_valid,
    ]
    for t in tests:
        t()
        print("OK", t.__name__)


if __name__ == "__main__":
    main()
