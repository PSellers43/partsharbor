"""Derive SOS-certified general-election roster expectations from beachheads.json."""
from __future__ import annotations

from typing import Any, Dict, List


def ballot_role_label(kind: str, person: dict, district: dict) -> str:
    party = (person.get("party") or "").strip().upper()
    if kind == "incumbent":
        return "Incumbent"
    if district.get("open_seat"):
        return f"Open seat – {party}" if party in ("R", "D") else "Open seat"
    return "Opponent"


def district_expected_entries(district: dict) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if district.get("open_seat"):
        for person in district.get("general_candidates") or []:
            entries.append(
                {
                    "name": person["name"],
                    "role": ballot_role_label("open_seat", person, district),
                    "party": person.get("party"),
                }
            )
        return entries
    inc = district.get("incumbent") or {}
    entries.append(
        {
            "name": inc["name"],
            "role": ballot_role_label("incumbent", inc, district),
            "party": inc.get("party"),
        }
    )
    for opp in district.get("known_opponents") or []:
        if (opp.get("ballot_status") or "general") == "primary_only":
            continue
        entries.append(
            {
                "name": opp["name"],
                "role": ballot_role_label("opponent", opp, district),
                "party": opp.get("party"),
            }
        )
    return entries


def certified_roster_by_district(beach: dict) -> Dict[str, List[Dict[str, Any]]]:
    return {d["id"]: district_expected_entries(d) for d in beach.get("districts") or []}
