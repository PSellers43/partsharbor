"""Shared poll schema helpers (build-time, no network)."""

from __future__ import annotations

import datetime as dt
from typing import Any

BEACHHEAD_IDS = ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"]

SPONSOR_TYPES = frozenset({"independent", "campaign", "party", "ie"})

PARTISAN_SPONSOR_TYPES = frozenset({"campaign", "party", "ie"})

PARTISAN_POLL_WEIGHT = 0.5


def parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def poll_field_end(poll: dict[str, Any]) -> dt.date | None:
    return parse_date(poll.get("field_end"))


def is_recent_poll(poll: dict[str, Any], gap_days: int, as_of: dt.date) -> bool:
    end = poll_field_end(poll)
    if not end:
        return False
    return (as_of - end).days <= gap_days


def sponsor_weight(sponsor_type: str | None) -> float:
    if sponsor_type in PARTISAN_SPONSOR_TYPES:
        return PARTISAN_POLL_WEIGHT
    return 1.0


def margin_from_toplines(toplines: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not toplines or len(toplines) < 2:
        return None
    sorted_rows = sorted(toplines, key=lambda r: float(r.get("pct") or 0), reverse=True)
    leader, trailer = sorted_rows[0], sorted_rows[1]
    return {
        "leader_name": leader.get("name"),
        "leader_party": leader.get("party"),
        "leader_pct": leader.get("pct"),
        "trailer_name": trailer.get("name"),
        "trailer_party": trailer.get("party"),
        "trailer_pct": trailer.get("pct"),
    }


def legacy_poll_row(poll: dict[str, Any]) -> dict[str, Any]:
    """Map released/internal poll object to legacy latest.json poll block."""
    margin = margin_from_toplines(poll.get("toplines") or [])
    out: dict[str, Any] = {
        "pollster": poll.get("pollster"),
        "sponsor": poll.get("sponsor"),
        "sponsor_type": poll.get("sponsor_type"),
        "sponsor_party": poll.get("sponsor_party"),
        "field_start": poll.get("field_start"),
        "field_end": poll.get("field_end"),
        "sample_n": poll.get("sample_n"),
        "population": poll.get("population"),
        "mode": poll.get("mode"),
        "moe_pct": poll.get("moe_pct"),
        "source_url": poll.get("source_url"),
        "source_label": poll.get("source_label"),
        "visibility": poll.get("visibility") or "public",
    }
    if margin:
        u = poll.get("undecided_pct")
        if u is not None:
            margin["undecided_pct"] = u
        out["margin"] = margin
    return out


def pick_best_poll(
    polls: list[dict[str, Any]],
    district_id: str,
    gap_days: int,
    as_of: dt.date,
) -> dict[str, Any] | None:
    """Most recent field_end within gap window for a district."""
    candidates = [p for p in polls if p.get("district_id") == district_id]
    recent = [p for p in candidates if is_recent_poll(p, gap_days, as_of)]
    if not recent:
        return None
    recent.sort(key=lambda p: poll_field_end(p) or dt.date.min, reverse=True)
    return recent[0]
