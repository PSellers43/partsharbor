"""Classify CAL-ACCESS IE support/oppose relative to the R beachhead side."""

from __future__ import annotations

import re
from typing import Iterable


def norm_name(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def roster_parties(beach_district: dict | None, money_dist: dict | None) -> list[tuple[str, str]]:
    """(display name, party) for people on the Nov general ballot."""
    out: list[tuple[str, str]] = []
    if beach_district:
        if beach_district.get("open_seat"):
            for person in beach_district.get("general_candidates") or []:
                if person.get("name") and person.get("party") in ("R", "D"):
                    out.append((person["name"], person["party"]))
        else:
            inc = beach_district.get("incumbent") or {}
            if inc.get("name") and inc.get("party") in ("R", "D"):
                out.append((inc["name"], inc["party"]))
            for opp in beach_district.get("known_opponents") or []:
                if (opp.get("ballot_status") or "general") == "primary_only":
                    continue
                if opp.get("name") and opp.get("party") in ("R", "D"):
                    out.append((opp["name"], opp["party"]))
    if money_dist:
        for c in money_dist.get("candidates") or []:
            party = c.get("party")
            name = c.get("name")
            if name and party in ("R", "D"):
                out.append((name, party))
    dedup: list[tuple[str, str]] = []
    seen = set()
    for name, party in out:
        key = norm_name(name)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((name, party))
    return dedup


def excluded_target_names(beach_district: dict | None) -> set[str]:
    if not beach_district:
        return set()
    names = []
    for person in beach_district.get("primary_non_advancing") or []:
        if person.get("name"):
            names.append(norm_name(person["name"]))
    return {n for n in names if n}


def party_for_target(target: str, roster: Iterable[tuple[str, str]]) -> str | None:
    tgt = norm_name(target)
    if not tgt or tgt == "UNKNOWN":
        return None
    for name, party in roster:
        n = norm_name(name)
        if not n:
            continue
        if n in tgt or tgt in n:
            return party
        last = n.split()[-1]
        if len(last) > 3 and last in tgt:
            return party
    return None


def ie_effect_on_r(side: str, target_party: str | None) -> str | None:
    """Return pro_r, anti_r, or None when side/target party cannot be resolved."""
    side_l = (side or "").lower()
    if side_l not in ("support", "oppose") or target_party not in ("R", "D"):
        return None
    if side_l == "support":
        return "pro_r" if target_party == "R" else "anti_r"
    return "anti_r" if target_party == "R" else "pro_r"


def classify_ie_row(side: str, target: str, roster: list[tuple[str, str]], excluded: set[str]) -> str | None:
    tgt_norm = norm_name(target)
    if tgt_norm and tgt_norm in excluded:
        return None
    party = party_for_target(target, roster)
    return ie_effect_on_r(side, party)
