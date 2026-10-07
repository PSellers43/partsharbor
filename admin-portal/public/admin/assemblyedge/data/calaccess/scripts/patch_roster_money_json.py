#!/usr/bin/env python3
"""One-off patch: align committed money / late-money JSON with SOS-certified roster (no CAL-ACCESS re-ingest)."""
from __future__ import annotations

import json
from pathlib import Path

from roster_from_beachheads import certified_roster_by_district

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "latest"
BEACHHEADS_PATH = ROOT / "beachheads.json"

# Roles / parties / names to apply (filer_id from existing matched committees)
CANDIDATE_PATCH = {
    "ad-58": {
        "1480137": None,  # Paco Licea — remove from general roster
        "1477348": {"role": "Incumbent", "party": "R", "name": "Leticia Castillo"},
        "1478397": {"role": "Opponent", "party": "D", "name": "Clarissa Cervantes"},
    },
    "ad-27": {
        "1476814": None,  # Soria — not on AD-27 ballot
        "1463062": None,  # Garcia Rose
        "1485456": {"role": "Open seat – D", "party": "D", "name": "Brian Pacheco"},
        "1478647": {"role": "Open seat – R", "party": "R", "name": "Mike Murphy"},
    },
}

# Remove by filer_id when patch value is None
REMOVE_FILER = {
    "ad-27": {"1476814", "1463062"},  # plus dynamic below
}

NAME_FIXES = {
    "Amy Slavensky": "Amy L. Slavensky",
    "Ida Obeso-Martinez": "Ida S. Obeso-Martinez",
    "Michael Murphy": "Mike Murphy",
}

PRIMARY_DROP_AD27 = {"Leticia Gonzalez", "Priya Lakireddy", "Joanna Garcia Rose", "Esmeralda Soria"}

PRIMARY_DROP_BY_DISTRICT = {
    "ad-7": {"Vance Taylor", "Chris Hoang"},
    "ad-47": {"Jason Byors", "Lucas Pinon"},
    "ad-58": {"Paco Licea"},
    "ad-74": {"Chris Duncan"},
    "ad-36": {"Tomas Oliva", "Oscar Ortiz", "Oscar F. Ortiz"},
    "ad-27": PRIMARY_DROP_AD27,
}

ROLE_PARTY_FIX = {
    "ad-7": {
        "Josh Hoover": ("Incumbent", "R"),
        "Amy L. Slavensky": ("Opponent", "D"),
        "Amy Slavensky": ("Opponent", "D"),
    },
    "ad-36": {
        "Jeff Gonzalez": ("Incumbent", "R"),
        "Ida S. Obeso-Martinez": ("Opponent", "D"),
        "Ida Obeso-Martinez": ("Opponent", "D"),
    },
    "ad-47": {
        "Greg Wallis": ("Incumbent", "R"),
        "Leila Namvar": ("Opponent", "D"),
    },
    "ad-74": {
        "Laurie Davies": ("Incumbent", "R"),
        "Sergio Farias": ("Opponent", "D"),
    },
    "ad-58": {
        "Leticia Castillo": ("Incumbent", "R"),
        "Clarissa Cervantes": ("Opponent", "D"),
    },
    "ad-27": {
        "Mike Murphy": ("Open seat – R", "R"),
        "Michael Murphy": ("Open seat – R", "R"),
        "Brian Pacheco": ("Open seat – D", "D"),
    },
}


def apply_certified_roster_filter(candidates: list, roster_entries: list) -> list:
    """Keep only SOS-certified general candidates; sync role and party from beachheads."""
    if not roster_entries:
        return candidates
    by_name = {e["name"]: e for e in roster_entries}
    allowed = set(by_name.keys())
    out = []
    for c in candidates:
        nm = c.get("name") or ""
        if nm in NAME_FIXES:
            nm = NAME_FIXES[nm]
            c = {**c, "name": nm}
        if nm not in allowed:
            continue
        exp = by_name[nm]
        out.append({**c, "role": exp["role"], "party": exp["party"]})
    out.sort(key=lambda x: (0 if x.get("role") == "Incumbent" else 1, x.get("name") or ""))
    if roster_entries and roster_entries[0].get("role", "").startswith("Open seat"):
        out.sort(key=lambda x: (0 if "R" in str(x.get("role")) else 1, x.get("name") or ""))
    return out


def patch_candidates(candidates: list, district_id: str, roster_entries: list | None = None) -> list:
    patch = CANDIDATE_PATCH.get(district_id, {})
    remove_filers = set(REMOVE_FILER.get(district_id, ()))
    out = []
    for c in candidates:
        fid = str(c.get("filer_id") or "")
        if district_id == "ad-27":
            if c.get("name") in PRIMARY_DROP_AD27:
                continue
            if fid in remove_filers:
                continue
        drop_names = PRIMARY_DROP_BY_DISTRICT.get(district_id, set())
        if c.get("name") in drop_names:
            continue
        if fid in patch:
            meta = patch[fid]
            if meta is None:
                continue
            c = {**c, **meta}
        nm = c.get("name")
        if nm in NAME_FIXES:
            c = {**c, "name": NAME_FIXES[nm]}
            nm = c["name"]
        fix = (ROLE_PARTY_FIX.get(district_id) or {}).get(nm)
        if fix:
            c = {**c, "role": fix[0], "party": fix[1]}
        out.append(c)
    # Swap order for AD-58: incumbent first
    if district_id == "ad-58":
        out.sort(key=lambda x: (0 if x.get("role") == "Incumbent" else 1, x.get("name") or ""))
    if district_id == "ad-27":
        out.sort(key=lambda x: (0 if "R" in str(x.get("role")) else 1, x.get("name") or ""))
    if roster_entries is not None:
        out = apply_certified_roster_filter(out, roster_entries)
    return out


def patch_money_doc(doc: dict, roster_by_district: dict) -> None:
    for did, dist in (doc.get("districts") or {}).items():
        dist["candidates"] = patch_candidates(
            dist.get("candidates") or [], did, roster_by_district.get(did)
        )
        for ie in dist.get("ie") or []:
            for t in ie.get("targets") or []:
                if t in NAME_FIXES:
                    pass  # targets are strings in list — patch in place below
        # fix IE target name strings
        for ie in dist.get("ie") or []:
            ie["targets"] = [NAME_FIXES.get(t, t) for t in (ie.get("targets") or [])]

    for row in doc.get("match_report") or []:
        did = row.get("id")
        if not did:
            continue
        row["candidates"] = patch_candidates(
            row.get("candidates") or [], did, roster_by_district.get(did)
        )


def build_filer_map(doc: dict) -> dict:
    m = {}
    for did, dist in (doc.get("districts") or {}).items():
        for c in dist.get("candidates") or []:
            fid = c.get("filer_id")
            if fid:
                m[str(fid)] = c.get("name") or ""
    return m


def patch_late_doc(doc: dict, filer_map: dict) -> None:
    for _did, dist in (doc.get("districts") or {}).items():
        for item in dist.get("recent_contributions") or []:
            cand = (item.get("candidate") or "").strip()
            if not cand or cand.lower() == "unknown":
                fid = str(item.get("committee_filer_id") or "")
                if fid in filer_map and filer_map[fid]:
                    item["candidate"] = filer_map[fid]


def main() -> None:
    with open(BEACHHEADS_PATH, encoding="utf-8") as f:
        beach = json.load(f)
    roster_by_district = certified_roster_by_district(beach)

    money_files = [
        LATEST / "money-by-district.json",
        LATEST / "money-by-district-2026-10-07.json",
        LATEST / "money-by-district-2026-10-06.json",
    ]
    for path in money_files:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        patch_money_doc(doc, roster_by_district)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        print(f"patched {path.name}")

    match_report_path = LATEST / "match-report.json"
    if match_report_path.exists():
        with open(match_report_path, encoding="utf-8") as f:
            mr = json.load(f)
        for row in mr.get("report") or []:
            did = row.get("id")
            if did:
                row["candidates"] = patch_candidates(
                    row.get("candidates") or [], did, roster_by_district.get(did)
                )
        with open(match_report_path, "w", encoding="utf-8") as f:
            json.dump(mr, f, indent=2)
            f.write("\n")
        print("patched match-report.json")

    with open(LATEST / "money-by-district.json", encoding="utf-8") as f:
        money = json.load(f)
    filer_map = build_filer_map(money)

    for path in [LATEST / "late-money-by-district.json", LATEST / "late-money-by-district-2026-10-07.json"]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        patch_late_doc(doc, filer_map)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        print(f"patched {path.name}")


if __name__ == "__main__":
    main()
