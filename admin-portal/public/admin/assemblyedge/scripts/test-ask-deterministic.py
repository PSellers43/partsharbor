#!/usr/bin/env python3
"""Smoke-test Ask the desk expected figures against repo JSON (no browser)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(rel: str):
    with open(ROOT / rel, encoding="utf-8") as f:
        return json.load(f)


def test_ie_ad58():
    money = load_json("data/calaccess/latest/money-by-district.json")
    dist = money["districts"]["ad-58"]
    total = sum(row["series"][-1] for row in dist["ie"])
    assert total > 400_000, total
    print(f"OK IE AD-58 week bucket total ${total:,.2f}")


def test_registration_compare():
    demo = load_json("data/demography/latest/demography-by-district.json")
    by_id = {d["id"]: d for d in demo["districts"]}
    a, b = by_id["ad-47"], by_id["ad-74"]
    dem_a = next(p for p in a["registration"]["parties"] if p["id"] == "dem")["pct"]
    dem_b = next(p for p in b["registration"]["parties"] if p["id"] == "dem")["pct"]
    print(f"OK registration AD-47 Dem {dem_a}% vs AD-74 Dem {dem_b}%")


def test_abev_ad36():
    abev = load_json("data/abev/latest/abev-by-district.json")
    row = next(d for d in abev["districts"] if d["id"] == "ad-36")
    g24 = row["baselines"]["g24"]
    assert g24["vbm_pct_of_sov_registration"] > 50
    print(f"OK AD-36 2024 VBM {g24['vbm_pct_of_sov_registration']}% of SOV reg")


def test_swing_ad7():
    with open(ROOT / "data/election-history/latest/ad-7-precincts.geojson", encoding="utf-8") as f:
        geo = json.load(f)
    count = 0
    for feat in geo["features"]:
        p = feat["properties"]
        m22 = (p.get("g22_asm") or {}).get("margin_dem")
        m24 = (p.get("g24_asm") or {}).get("margin_dem")
        if m22 is None or m24 is None:
            continue
        if m24 - m22 < -0.5:
            count += 1
    assert count > 50, count
    print(f"OK AD-7 swing toward R precinct count {count}")


def test_late_money_ad36():
    data = load_json("data/calaccess/latest/late-money-by-district.json")
    dist = data["districts"]["ad-36"]
    seven = dist["totals"]["seven_day"]
    assert seven > 100_000, seven
    print(f"OK AD-36 late money 7-day ${seven:,.2f}")


def test_social_gonzalez_ad36():
    feed = load_json("data/social/latest/social-feed.json")
    block = feed["districts"]["AD-36"]
    gonz = [
        p
        for p in block["posts"]
        if "gonzalez" in (p.get("candidate") or "").lower()
    ]
    assert len(gonz) >= 8, len(gonz)
    print(f"OK AD-36 Gonzalez candidate posts {len(gonz)}")


def test_social_attacks_ad36():
    feed = load_json("data/social/latest/social-feed.json")
    posts = feed["districts"]["AD-36"]["posts"]
    post_attacks = [p for p in posts if "attack" in (p.get("flags") or [])]
    mention_attacks = [
        m
        for m in feed.get("mentions", [])
        if m.get("district") == "AD-36" and "attack" in (m.get("flags") or [])
    ]
    total = len(post_attacks) + len(mention_attacks)
    assert total >= 1, total
    print(f"OK AD-36 attack-flagged items {total} (posts {len(post_attacks)}, mentions {len(mention_attacks)})")


def test_social_sentiment_ad36_trend():
    feed = load_json("data/social/latest/social-feed.json")
    rows = [r for r in feed.get("sentiment_history", []) if r.get("district") == "AD-36"]
    assert len(rows) >= 2, len(rows)
    nets = [r["net"] for r in rows if r.get("net") is not None]
    assert len(nets) >= 2, nets
    delta = nets[-1] - nets[0]
    print(f"OK AD-36 sentiment {len(rows)} days · net Δ {delta:+.3f} (latest {nets[-1]:+.3f})")


def test_rancho_tight():
    with open(ROOT / "data/election-history/latest/ad-7-precincts.geojson", encoding="utf-8") as f:
        geo = json.load(f)
    tight = 0
    for feat in geo["features"]:
        p = feat["properties"]
        if p.get("place_primary") != "Rancho Cordova":
            continue
        m = (p.get("g24_asm") or {}).get("margin_dem")
        if m is not None and abs(m) <= 2:
            tight += 1
    assert tight >= 1, tight
    print(f"OK Rancho Cordova within 2pts (2024) count {tight}")


def main():
    tests = [
        test_ie_ad58,
        test_registration_compare,
        test_abev_ad36,
        test_swing_ad7,
        test_late_money_ad36,
        test_social_gonzalez_ad36,
        test_social_attacks_ad36,
        test_social_sentiment_ad36_trend,
        test_rancho_tight,
    ]
    for t in tests:
        t()
    print("All deterministic smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
