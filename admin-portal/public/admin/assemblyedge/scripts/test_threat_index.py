#!/usr/bin/env python3
"""Unit tests for Threat Index computation."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "threat-index" / "scripts"))

from ti_ie_direction import ie_effect  # noqa: E402
from ti_compute import (  # noqa: E402
    BASE_WEIGHTS,
    WEIGHTS,
    ad_surge_raw,
    composite_ti,
    compute_district_ti,
    effective_weights,
    ie_pressure_raw,
    money_velocity_raw,
    narrative_score_from_count,
    normalize_across,
    normalize_ad_scores,
    poll_is_recent,
    poll_movement_score,
    poll_sponsor_weight,
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
    scores = {"money": 80, "ie": 60, "ads": 55, "narrative": 40, "polls": 50}
    ti = composite_ti(scores)
    expected = sum(WEIGHTS[k] * scores[k] for k in WEIGHTS)
    assert ti == round(expected)


def test_ad_surge_raw_increases_with_spend():
    low = [{"week_start": "2026-09-20", "spend_usd": 1000}, {"week_start": "2026-09-27", "spend_usd": 1100}]
    high = [{"week_start": "2026-09-20", "spend_usd": 10000}, {"week_start": "2026-09-27", "spend_usd": 25000}]
    assert ad_surge_raw(high) > ad_surge_raw(low)


def test_no_matched_ads_scores_zero_not_normalized_mid():
    raw = {"ad-7": 5.0, "ad-27": 0.0}
    has = {"ad-7": True, "ad-27": False}
    out = normalize_ad_scores(raw, has)
    assert out["ad-27"] == 0.0
    assert out["ad-7"] > 0.0


def test_partisan_poll_downweighted():
    as_of = dt.date(2026, 10, 8)
    poll_row = {
        "poll": {
            "pollster": "Test",
            "field_end": "2026-10-01",
            "sponsor_type": "campaign",
            "margin": {
                "leader_party": "R",
                "leader_pct": 50,
                "trailer_party": "D",
                "trailer_pct": 45,
            },
        }
    }
    assert poll_sponsor_weight("campaign") == 0.5
    score, blurb, partisan = poll_movement_score(poll_row, 90, as_of)
    assert partisan is True
    assert "50%" in blurb or "0.5" in blurb.lower() or "50" in blurb
    assert score < 42


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
        assert ads.get("unavailable") is not True
        assert ads["score"] is not None
        assert ads["weight"] > 0
        assert "Google" in ads["blurb"]
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
    late_high = {
        "totals": {
            "seven_day": 500000,
            "ie_seven_day": 400000,
            "ie_seven_day_anti_r": 200000,
            "ie_seven_day_pro_r": 50000,
        },
        "daily_buckets": [{"amount": 100}] * 20,
    }
    late_low = {
        "totals": {
            "seven_day": 1000,
            "ie_seven_day": 500,
            "ie_seven_day_anti_r": 200,
            "ie_seven_day_pro_r": 100,
        },
        "daily_buckets": [{"amount": 10}] * 20,
    }
    assert money_velocity_raw(late_high) > money_velocity_raw(late_low)
    assert ie_pressure_raw(late_high) > ie_pressure_raw(late_low)
    assert ie_pressure_raw({"totals": {"ie_seven_day": 999999, "ie_seven_day_anti_r": 0}}) == 0.0


def test_official_lean_json():
    path = ROOT / "data" / "election-history" / "official" / "asm-2024-general-sov.json"
    assert path.exists()
    doc = json.loads(path.read_text(encoding="utf-8"))
    ad7 = doc["districts"]["ad-7"]
    assert ad7["lean"] == "R+7.3"
    ad27 = doc["districts"]["ad-27"]
    assert ad27["lean"] == "D+7.8"
    assert doc["districts"]["ad-58"]["lean"] == "R+0.4"
    assert "Middleton" in doc["districts"]["ad-7"]["loser"]


def test_ie_effect_oppose_slavensky_is_pro_r():
    roster = {
        "incumbent": {"name": "Josh Hoover", "party": "R"},
        "known_opponents": [{"name": "Amy L. Slavensky", "party": "D", "ballot_status": "general"}],
    }
    assert ie_effect("oppose", "Amy L. Slavensky", roster) == "pro_r"


def test_ad7_zero_anti_r_lowest_ie_pressure():
    late = json.loads((ROOT / "data" / "calaccess" / "latest" / "late-money-by-district.json").read_text())
    raw = {}
    for did in ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"]:
        row = late.get("districts", {}).get(did)
        raw[did] = ie_pressure_raw(row)
    assert raw["ad-7"] == min(raw.values())


def test_late_money_anti_r_within_seven_day():
    late = json.loads((ROOT / "data" / "calaccess" / "latest" / "late-money-by-district.json").read_text())
    for did, row in (late.get("districts") or {}).items():
        t = row.get("totals") or {}
        anti = float(t.get("ie_seven_day_anti_r") or 0)
        total = float(t.get("ie_seven_day") or 0)
        assert anti <= total + 0.01, f"{did}: anti-R {anti} > 7-day IE {total}"


def test_precinct_g24_rollup_near_sos():
    official_path = ROOT / "data" / "election-history" / "official" / "asm-2024-general-sov.json"
    idx_path = ROOT / "data" / "election-history" / "latest" / "election-history-index.json"
    if not official_path.is_file() or not idx_path.is_file():
        return
    official = json.loads(official_path.read_text(encoding="utf-8"))
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    meta_by_id = {d["id"]: d for d in idx.get("districts") or []}
    eh = ROOT / "data" / "election-history" / "latest"
    for did, row in official.get("districts", {}).items():
        geo_path = eh / f"{did}-precincts.geojson"
        if not geo_path.is_file():
            continue
        g24_cov = float(meta_by_id.get(did, {}).get("g24_results_pct") or 0)
        g = json.loads(geo_path.read_text(encoding="utf-8"))
        dem_v = rep_v = 0.0
        for feat in g.get("features") or []:
            g24 = (feat.get("properties") or {}).get("g24_asm")
            if not g24 or not g24.get("votes_two_party"):
                continue
            v = float(g24["votes_two_party"])
            dem_pct = g24.get("dem_pct")
            if dem_pct is None:
                continue
            dem_v += v * float(dem_pct) / 100.0
            rep_v += v * (100.0 - float(dem_pct)) / 100.0
        tot = dem_v + rep_v
        assert tot > 0, f"{did}: no g24 votes in GeoJSON"
        sos_tot = float(row["dem_votes"]) + float(row["rep_votes"])
        margin_r = rep_v / tot * 100.0 - dem_v / tot * 100.0
        if g24_cov >= 90.0:
            assert abs(tot - sos_tot) / sos_tot <= 0.02, f"{did}: roll-up {tot:.0f} vs SOS {sos_tot:.0f} (g24 cov {g24_cov}%)"
            assert abs(margin_r - float(row["margin_r_pct"])) <= 0.5, f"{did}: margin {margin_r:.2f} vs SOS {row['margin_r_pct']}"
        else:
            assert abs(margin_r - float(row["margin_r_pct"])) <= 2.0, (
                f"{did}: partial g24 shape coverage ({g24_cov}%) — margin {margin_r:.2f} vs SOS {row['margin_r_pct']}"
            )


def main():
    tests = [
        test_weights_sum_to_one,
        test_effective_weights_renormalize_without_polls,
        test_narrative_zero_is_zero,
        test_status_thresholds,
        test_composite_ti_weighted,
        test_ad_surge_raw_increases_with_spend,
        test_no_matched_ads_scores_zero_not_normalized_mid,
        test_partisan_poll_downweighted,
        test_poll_excluded_no_fake_score,
        test_normalize_spreads_values,
        test_late_money_inputs_change_ti,
        test_ie_effect_oppose_slavensky_is_pro_r,
        test_late_money_anti_r_within_seven_day,
        test_ad7_zero_anti_r_lowest_ie_pressure,
        test_official_lean_json,
        test_precinct_g24_rollup_near_sos,
        test_bundle_json_valid,
    ]
    for t in tests:
        t()
        print("OK", t.__name__)


if __name__ == "__main__":
    main()
