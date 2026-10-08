#!/usr/bin/env python3
"""Smoke tests for MajorityIQ data builders (no network when fixtures present)."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(rel_path: str, name: str):
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


class TestCountyMaps(unittest.TestCase):
    def test_election_history_counties(self):
        eh = load_module("data/election-history/scripts/build_election_history_precincts.py", "eh")
        self.assertIn(47, eh.COUNTY_FIPS["27"])
        self.assertIn(73, eh.COUNTY_FIPS["74"])
        self.assertIn(71, eh.COUNTY_FIPS["36"])

    def test_abev_counties_match_election(self):
        eh = load_module("data/election-history/scripts/build_election_history_precincts.py", "eh")
        abev = load_module("data/abev/scripts/build_abev_json.py", "abev")
        for dist, cids in eh.COUNTY_FIPS.items():
            self.assertEqual(set(cids), set(abev.COUNTIES_BY_AD[dist]))


class TestSentimentLexicon(unittest.TestCase):
    def test_scores_text_not_only_flags(self):
        es = load_module("data/social/scripts/enrich_sentiment.py", "es")
        post = {"text": "Thank you to everyone who joined our community town hall today!", "flags": []}
        score, label = es.score_post(post)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)
        self.assertEqual(label, "positive")

    def test_attack_text_negative(self):
        es = load_module("data/social/scripts/enrich_sentiment.py", "es")
        post = {"text": "My opponent's corrupt record is a disaster for our district.", "flags": []}
        score, _ = es.score_post(post)
        self.assertIsNotNone(score)
        self.assertLess(score, 0)


class TestElectionIndex(unittest.TestCase):
    def test_index_has_coverage_fields(self):
        idx_path = ROOT / "data/election-history/latest/election-history-index.json"
        if not idx_path.is_file():
            self.skipTest("election history not built yet")
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        for row in idx.get("districts") or []:
            self.assertIn("area_coverage_pct", row)
            self.assertIn("gaps", row)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
