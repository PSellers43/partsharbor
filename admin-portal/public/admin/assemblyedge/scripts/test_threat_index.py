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
    BASE_WEIGHTS,
    WEIGHTS,
    composite_ti,
    compute_district_ti,
    effective_weights,
    ie_pressure_raw,
    money_velocity_raw,
    narrative_score_from_count,
    normalize_across,
    poll_is_recent,
    status_from_ti,
)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_effective_weights_renormalize_without_polls():
    w = effective_weights(False)
    assert "polls" not in w
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["money"] > BASE_WEIGHTS["money"]


def test_narrative_zero_is_zero():
    assert narrative_score_from_count(0) == 0
    assert narrative_score_from_count(3) == 60


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


def test_poll_excluded_no_fake_score():
    as_of = dt.date(2026, 10, 8)
    poll_row = {"gap": {"message": "No public horse-race poll in the last 90 days"}}
    out = compute_district_ti(
        "ad-7",
        {"totals": {"seven_day": 1000, "ie_seven_day": 5000, "ie_oppose": 1, "ie_support": 1}, "daily_buckets": [{"amount": 1}] * 20},
        poll_row,
        [],
        as_of,
        90,
        money_scores={"ad-7": 50},
        ie_scores={"ad-7": 50},
    )
    polls = next(f for f in out["factors"] if f["id"] == "polls")
    assert polls.get("unavailable") is True
    assert polls["score"] is None
    assert "Excluded" in polls["blurb"]
    assert out["poll_included"] is False
    narr = next(f for f in out["factors"] if f["id"] == "narrative")
    assert narr["score"] == 0


def test_normalize_spreads_values():
    raw = {"ad-7": 1.0, "ad-74": 5.0}
    out = normalize_across(raw)
    assert out["ad-7"] < out["ad-74"]


def test_precinct_g24_rollup_within_sov_tolerance():
    sov_path = ROOT / "data" / "election-history" / "official" / "asm-2024-general-sov.json"
    assert sov_path.exists(), "Missing official asm-2024-general-sov.json"
    official = json.loads(sov_path.read_text(encoding="utf-8"))
    eh = ROOT / "data" / "election-history" / "latest"
    idx_path = eh / "election-history-index.json"
    manifest = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.is_file() else {}
    meta_by_id = {r["id"]: r for r in manifest.get("districts") or []}
    for did, row in (official.get("districts") or {}).items():
        geo_path = eh / f"{did}-precincts.geojson"
        assert geo_path.exists(), f"Missing {geo_path.name}"
        g = json.loads(geo_path.read_text(encoding="utf-8"))
        dem_v = rep_v = 0.0
        for feat in g.get("features") or []:
            g24 = (feat.get("properties") or {}).get("g24_asm")
            if not g24 or not g24.get("votes_two_party"):
                continue
            v = float(g24["votes_two_party"])
            dem_v += v * float(g24["dem_pct"]) / 100.0
            rep_v += v * (100.0 - float(g24["dem_pct"])) / 100.0
        tot = dem_v + rep_v
        sos_tot = float(row["dem_votes"]) + float(row["rep_votes"])
        assert sos_tot > 0
        g24_cov = float(meta_by_id.get(did, {}).get("g24_results_pct") or 0)
        if g24_cov < 90.0:
            assert tot > 0, f"{did}: no g24 votes in precinct bundle (SWDB/shape coverage {g24_cov}%)"
            continue
        assert abs(tot - sos_tot) / sos_tot <= 0.02, f"{did} vote total off >2%: rollup={int(tot)} sos={int(sos_tot)}"
        margin_r = rep_v / tot * 100 - dem_v / tot * 100
        assert abs(margin_r - float(row["margin_r_pct"])) <= 0.5, f"{did} margin off >0.5pt"


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
        polls = next(f for f in row["factors"] if f["id"] == "polls")
        if did == "ad-7":
            assert polls.get("unavailable") is True
            assert polls["score"] is None
        narr = next(f for f in row["factors"] if f["id"] == "narrative")
        assert narr["score"] == 0 or "headline" in narr["blurb"].lower()
        assert data["narrative"][did]
        assert data["rival"][did]["opponent"]
        assert data["alerts"][did]


def test_late_money_inputs_change_ti():
    late_high = {"totals": {"seven_day": 500000, "ie_seven_day": 400000, "ie_oppose": 200000, "ie_support": 50000}, "daily_buckets": [{"amount": 100}] * 20}
    late_low = {"totals": {"seven_day": 1000, "ie_seven_day": 500, "ie_oppose": 200, "ie_support": 100}, "daily_buckets": [{"amount": 10}] * 20}
    assert money_velocity_raw(late_high) > money_velocity_raw(late_low)
    assert ie_pressure_raw(late_high) > ie_pressure_raw(late_low)


def main():
    tests = [
        test_weights_sum_to_one,
        test_effective_weights_renormalize_without_polls,
        test_narrative_zero_is_zero,
        test_status_thresholds,
        test_composite_ti_weighted,
        test_poll_excluded_no_fake_score,
        test_normalize_spreads_values,
        test_late_money_inputs_change_ti,
        test_precinct_g24_rollup_within_sov_tolerance,
        test_bundle_json_valid,
    ]
    for t in tests:
        t()
        print("OK", t.__name__)


if __name__ == "__main__":
    main()
