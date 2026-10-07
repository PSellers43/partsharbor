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
        test_rancho_tight,
    ]
    for t in tests:
        t()
    print("All deterministic smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
