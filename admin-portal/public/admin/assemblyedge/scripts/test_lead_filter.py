#!/usr/bin/env python3
"""Tests for poll lead relevance filter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "polls" / "scripts"))

from lead_filter import is_relevant_lead  # noqa: E402


def load_beach():
    return json.loads((ROOT / "data" / "calaccess" / "beachheads.json").read_text(encoding="utf-8"))


def test_accepts_ad_and_poll():
    beach = load_beach()
    lead = {
        "title": "New poll shows tight AD-7 California Assembly race in Sacramento",
        "link": "https://example.com/1",
    }
    assert is_relevant_lead(lead, beach)


def test_rejects_poll_without_beachhead():
    beach = load_beach()
    lead = {"title": "National presidential poll tracker update", "link": "https://example.com/2"}
    assert not is_relevant_lead(lead, beach)


def test_accepts_candidate_name_and_survey():
    beach = load_beach()
    lead = {
        "title": "Internal survey memo: Josh Hoover leads Slavensky in California Assembly contest",
        "link": "https://example.com/3",
    }
    assert is_relevant_lead(lead, beach)


def test_rejects_iowa_ad27_false_positive():
    beach = load_beach()
    lead = {
        "title": 'Poll shows Chris Jones "within striking distance" of Mike Naig - Bleeding Heartland',
        "link": "https://example.com/iowa",
    }
    assert not is_relevant_lead(lead, beach)


def main():
    for fn in [
        test_accepts_ad_and_poll,
        test_rejects_poll_without_beachhead,
        test_accepts_candidate_name_and_survey,
        test_rejects_iowa_ad27_false_positive,
    ]:
        fn()
        print("OK", fn.__name__)


if __name__ == "__main__":
    main()
