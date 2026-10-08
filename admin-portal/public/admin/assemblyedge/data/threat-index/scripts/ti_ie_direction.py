"""Classify CAL-ACCESS IE support/oppose relative to Republican beachhead candidates."""

from __future__ import annotations

import re
from typing import Any


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper()).strip()


def roster_people(roster: dict | None) -> list[tuple[str, str]]:
    """(normalized name, party R|D) for 2026 general-election candidates."""
    if not roster:
        return []
    out: list[tuple[str, str]] = []
    inc = roster.get("incumbent") or {}
    if inc.get("name") and inc.get("party") in ("R", "D"):
        out.append((_norm(inc["name"]), inc["party"]))
    for opp in roster.get("known_opponents") or []:
        if opp.get("ballot_status") == "general" and opp.get("name") and opp.get("party") in ("R", "D"):
            out.append((_norm(opp["name"]), opp["party"]))
    for cand in roster.get("general_candidates") or []:
        if cand.get("name") and cand.get("party") in ("R", "D"):
            out.append((_norm(cand["name"]), cand["party"]))
    return out


def target_party(target: str, roster: dict | None) -> str | None:
    tgt = _norm(target)
    if not tgt or tgt == "UNKNOWN":
        return None
    for name, party in roster_people(roster):
        if not name:
            continue
        if tgt == name or name in tgt or tgt in name:
            return party
        last = name.split()[-1]
        if len(last) > 3 and last in tgt:
            return party
    return None


def excluded_target_names(roster: dict | None) -> set[str]:
    if not roster:
        return set()
    names = []
    for person in roster.get("primary_non_advancing") or []:
        if person.get("name"):
            names.append(_norm(person["name"]))
    return {n for n in names if n}


def is_ballot_target(target: str, roster: dict | None) -> bool:
    tgt = _norm(target)
    if tgt and tgt in excluded_target_names(roster):
        return False
    return target_party(target, roster) is not None


def ie_effect(side: str, target: str, roster: dict | None) -> str | None:
    """
    pro_r: supports R or opposes D (helps Republican side).
    anti_r: supports D or opposes R (pressure on Republican / open-seat R nominee).
    """
    tgt = _norm(target)
    if tgt and tgt in excluded_target_names(roster):
        return None
    party = target_party(target, roster)
    if not party:
        return None
    s = (side or "").lower()
    if s not in ("support", "oppose"):
        return None
    if s == "support":
        return "pro_r" if party == "R" else "anti_r"
    return "anti_r" if party == "R" else "pro_r"


def aggregate_ie_effects(ie_rows: list[dict], roster: dict | None) -> dict[str, float]:
    totals = {"ie_pro_r": 0.0, "ie_anti_r": 0.0, "ie_unknown_target": 0.0}
    for row in ie_rows or []:
        spend = float(row.get("spend") or 0)
        if spend <= 0:
            continue
        targets = row.get("targets") or []
        if not targets and row.get("target"):
            targets = [row["target"]]
        if not targets:
            totals["ie_unknown_target"] += spend
            continue
        effect = None
        for t in targets:
            effect = ie_effect(row.get("side") or "", str(t), roster)
            if effect:
                break
        if effect == "pro_r":
            totals["ie_pro_r"] += spend
        elif effect == "anti_r":
            totals["ie_anti_r"] += spend
        else:
            totals["ie_unknown_target"] += spend
    return totals


