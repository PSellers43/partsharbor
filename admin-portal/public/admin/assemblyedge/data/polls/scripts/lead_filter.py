"""Filter RSS poll leads to beachhead-relevant items only."""

from __future__ import annotations

import re
from typing import Any

POLL_KEYWORDS = re.compile(r"\b(poll|survey|memo|topline|ballot test)\b", re.I)
DISTRICT_RE = re.compile(r"\b(?:AD|Assembly District|District)[\s-]*(\d{1,2})\b", re.I)

BEACHHEAD_IDS = frozenset({"ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"})


def _first_token(name: str | None) -> str | None:
    parts = (name or "").split()
    return parts[0] if parts else None


def _last_token(name: str | None) -> str | None:
    parts = (name or "").split()
    return parts[-1].lower() if parts else None


def build_beachhead_index(beach: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return (district numbers as str, lowercase last-name tokens)."""
    dist_nos: set[str] = set()
    names: set[str] = set()
    for row in beach.get("districts") or []:
        did = row.get("id")
        if did not in BEACHHEAD_IDS:
            continue
        if row.get("dist_no") is not None:
            dist_nos.add(str(int(row["dist_no"])))
        if row.get("open_seat"):
            for cand in row.get("general_candidates") or []:
                last = _last_token(cand.get("name"))
                first = _first_token(cand.get("name"))
                if last:
                    names.add(last)
                if first:
                    names.add(first.lower())
        else:
            inc = row.get("incumbent") or {}
            for nm in (inc.get("name"),):
                last = _last_token(nm)
                if last:
                    names.add(last)
            for opp in row.get("known_opponents") or []:
                last = _last_token(opp.get("name"))
                if last:
                    names.add(last)
    return dist_nos, names


def mentions_beachhead(blob: str, dist_nos: set[str], name_tokens: set[str]) -> bool:
    lower = blob.lower()
    for num in dist_nos:
        if re.search(rf"\b(ad[\s-]*{num}|assembly district[\s-]*{num}|district[\s-]*{num})\b", lower):
            return True
        if re.search(rf"\b{num}\b", lower) and "assembly" in lower:
            return True
    for tok in name_tokens:
        if len(tok) >= 3 and re.search(rf"\b{re.escape(tok)}\b", lower):
            return True
    return False


def is_relevant_lead(lead: dict[str, Any], beach: dict[str, Any]) -> bool:
    blob = f"{lead.get('title') or ''} {lead.get('link') or ''}"
    if not POLL_KEYWORDS.search(blob):
        return False
    dist_nos, names = build_beachhead_index(beach)
    return mentions_beachhead(blob, dist_nos, names)


def filter_leads(leads: list[dict[str, Any]], beach: dict[str, Any]) -> list[dict[str, Any]]:
    kept = [lead for lead in leads if is_relevant_lead(lead, beach)]
    kept.sort(key=lambda x: x.get("date") or "", reverse=True)
    return kept
