"""Threat Index computation — pure functions (unit-tested, no I/O)."""

from __future__ import annotations

import datetime as dt
from typing import Any

# Polls may be excluded per district (weights renormalized). Ad surge uses Google weekly spend.
BASE_WEIGHTS = {
    "money": 0.25,
    "ie": 0.20,
    "ads": 0.20,
    "narrative": 0.20,
    "polls": 0.15,
}

# Back-compat name used in tests
WEIGHTS = BASE_WEIGHTS

NARRATIVE_POINTS_PER_HEADLINE = 20

ELEVATED_MIN = 65
WATCH_MIN = 45


def parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def status_from_ti(ti: float) -> str:
    if ti >= ELEVATED_MIN:
        return "elevated"
    if ti >= WATCH_MIN:
        return "watch"
    return "stable"


def effective_weights(poll_included: bool) -> dict[str, float]:
    if poll_included:
        return dict(BASE_WEIGHTS)
    active = {k: v for k, v in BASE_WEIGHTS.items() if k != "polls"}
    total = sum(active.values())
    return {k: v / total for k, v in active.items()}


def ad_surge_raw(weekly_rows: list[dict[str, Any]] | None) -> float:
    """
    Google weekly spend signal: recent level × week-over-week change.
    Uses the two most recent weeks in the district rollup (7-day buckets in source data).
    """
    if not weekly_rows or len(weekly_rows) < 1:
        return 0.0
    ordered = sorted(weekly_rows, key=lambda r: r.get("week_start") or "")
    last = float(ordered[-1].get("spend_usd") or 0)
    prior = float(ordered[-2].get("spend_usd") or 0) if len(ordered) >= 2 else 0.0
    if prior > 0:
        wow = (last - prior) / prior
    elif last > 0:
        wow = 1.0
    else:
        wow = 0.0
    import math

    recent14 = last + prior
    if len(ordered) >= 4:
        recent14 = sum(float(x.get("spend_usd") or 0) for x in ordered[-4:])
    level = math.log1p(recent14)
    return level * (1.0 + max(-0.5, min(2.0, wow)))


def ad_surge_blurb(weekly_rows: list[dict[str, Any]] | None, score: int) -> str:
    if not weekly_rows:
        return (
            "No matched Google advertisers for this district in the transparency bundle. "
            "Score 0 — Meta not included."
        )
    ordered = sorted(weekly_rows, key=lambda r: r.get("week_start") or "")
    last = ordered[-1]
    prior = ordered[-2] if len(ordered) >= 2 else None
    last_amt = float(last.get("spend_usd") or 0)
    prior_amt = float(prior.get("spend_usd") or 0) if prior else 0.0
    wow_pct = ((last_amt - prior_amt) / prior_amt * 100.0) if prior_amt > 0 else None
    wow_txt = f"{wow_pct:+.0f}% vs prior week" if wow_pct is not None else "prior week $0 (change n/a)"
    return (
        "Google Political Ads Transparency weekly spend (US advertisers only). "
        f"Formula: rank across six beachheads of log1p(≈14d spend) × (1 + clamp(WoW, −50%, +200%)). "
        f"Latest week starting {last.get('week_start')}: ${last_amt:,.0f} ({wow_txt}). "
        f"District score after cross-beachhead normalization: {score}. Meta not included."
    )


def narrative_score_from_count(count_7d: int) -> int:
    """Transparent: 0 headlines → 0; each headline in last 7d adds 20 points, cap 100."""
    return min(100, max(0, int(count_7d) * NARRATIVE_POINTS_PER_HEADLINE))


def narrative_blurb(count_7d: int) -> str:
    score = narrative_score_from_count(count_7d)
    return (
        f"Rule: score = min(100, {NARRATIVE_POINTS_PER_HEADLINE} × headlines in last 7 days). "
        f"This district: {count_7d} headline(s) → {score}. "
        "Headlines from Google News RSS at build time."
    )


def money_velocity_raw(late_row: dict[str, Any] | None) -> float:
    """Higher = more late-cycle money velocity (contributions + IE in daily buckets)."""
    if not late_row:
        return 0.0
    totals = late_row.get("totals") or {}
    seven = float(totals.get("seven_day") or 0)
    ie7 = float(totals.get("ie_seven_day") or 0)
    buckets = late_row.get("daily_buckets") or []
    wow = 0.0
    if len(buckets) >= 14:
        recent = sum(float(b.get("amount") or 0) for b in buckets[-7:])
        prior = sum(float(b.get("amount") or 0) for b in buckets[-14:-7])
        if prior > 0:
            wow = (recent - prior) / prior
        elif recent > 0:
            wow = 1.0
    import math

    activity = math.log1p(seven + ie7)
    return activity * (1.0 + max(-0.5, min(2.0, wow)))


def ie_pressure_raw(late_row: dict[str, Any] | None) -> float:
    if not late_row:
        return 0.0
    totals = late_row.get("totals") or {}
    ie7 = float(totals.get("ie_seven_day") or 0)
    oppose = float(totals.get("ie_oppose") or 0)
    support = float(totals.get("ie_support") or 0)
    import math

    pressure = math.log1p(ie7)
    total_ie = oppose + support
    if total_ie > 0:
        oppose_share = oppose / total_ie
        pressure *= 0.75 + 0.5 * oppose_share
    return pressure


def narrative_raw(news_items: list[dict[str, Any]], as_of: dt.date) -> float:
    count_7d = 0
    for item in news_items or []:
        pub = parse_date(item.get("pub_date"))
        if pub and (as_of - pub).days <= 7:
            count_7d += 1
    return float(count_7d)


def poll_is_recent(poll_row: dict[str, Any] | None, gap_days: int, as_of: dt.date) -> bool:
    if not poll_row or not poll_row.get("poll"):
        return False
    end = parse_date(poll_row["poll"].get("field_end"))
    if not end:
        return False
    return (as_of - end).days <= gap_days


def poll_movement_score(poll_row: dict[str, Any], gap_days: int, as_of: dt.date) -> tuple[float, str]:
    """Score only when poll is recent; caller must gate with poll_is_recent."""
    poll = poll_row["poll"]
    margin = poll.get("margin") or {}
    leader = margin.get("leader_party")
    spread = abs(float(margin.get("leader_pct") or 0) - float(margin.get("trailer_pct") or 0))
    field_end = poll.get("field_end") or "—"
    if leader == "D":
        base = 78.0 - min(spread, 30.0)
    elif leader == "R":
        base = 42.0 - min(spread / 3.0, 12.0)
    else:
        base = 50.0
    blurb = f"Recent public poll ({poll.get('pollster')}, field end {field_end}) — in {gap_days}-day window."
    return base, blurb


def poll_excluded_blurb(poll_row: dict[str, Any] | None, gap_days: int, as_of: dt.date) -> str:
    if not poll_row:
        return f"Excluded from composite — no polling row on file."
    poll = poll_row.get("poll")
    if not poll:
        msg = (poll_row.get("gap") or {}).get("message") or "No public horse-race poll"
        return f"Excluded from composite — {msg}."
    field_end = poll.get("field_end") or "—"
    if not poll_is_recent(poll_row, gap_days, as_of):
        return (
            f"Excluded from composite — latest public poll ended {field_end} "
            f"(outside {gap_days}-day window); not scored as movement."
        )
    return "Excluded from composite — no qualifying poll."


def normalize_across(raw_by_id: dict[str, float], floor: float = 18.0, ceiling: float = 95.0) -> dict[str, float]:
    if not raw_by_id:
        return {}
    vals = list(raw_by_id.values())
    mn, mx = min(vals), max(vals)
    out: dict[str, float] = {}
    for k, v in raw_by_id.items():
        if mx == mn:
            out[k] = (floor + ceiling) / 2
        else:
            out[k] = floor + (ceiling - floor) * (v - mn) / (mx - mn)
    return out


def composite_ti(factor_scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    w = weights or BASE_WEIGHTS
    total = 0.0
    for key, wt in w.items():
        total += wt * float(factor_scores.get(key) or 0)
    return round(min(100.0, max(0.0, total)))


def compute_district_ti(
    district_id: str,
    late_row: dict[str, Any] | None,
    poll_row: dict[str, Any] | None,
    news_items: list[dict[str, Any]],
    as_of: dt.date,
    gap_days: int,
    *,
    money_scores: dict[str, float],
    ie_scores: dict[str, float],
    ad_scores: dict[str, float] | None = None,
    ad_weekly_by_district: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    narr_count = int(narrative_raw(news_items, as_of))
    narr_score = narrative_score_from_count(narr_count)

    poll_included = poll_is_recent(poll_row, gap_days, as_of)
    weights = effective_weights(poll_included)

    ad_sc = (ad_scores or {}).get(district_id, 50.0 if ad_scores else 0.0)
    weekly_rows = (ad_weekly_by_district or {}).get(district_id) or []

    factor_scores: dict[str, float] = {
        "money": money_scores.get(district_id, 50.0),
        "ie": ie_scores.get(district_id, 50.0),
        "ads": float(ad_sc),
        "narrative": float(narr_score),
    }
    poll_blurb = poll_excluded_blurb(poll_row, gap_days, as_of)
    poll_score_display: int | None = None
    poll_trend = "flat"

    if poll_included and poll_row:
        poll_val, poll_blurb = poll_movement_score(poll_row, gap_days, as_of)
        factor_scores["polls"] = poll_val
        poll_score_display = int(round(poll_val))
        poll_trend = "down" if poll_val < 45 else "up" if poll_val > 55 else "flat"

    ti = composite_ti(factor_scores, weights)
    st = status_from_ti(ti)

    money_blurb = _money_blurb(late_row)
    ie_blurb = _ie_blurb(late_row)

    factors = [
        {
            "id": "money",
            "label": "Money velocity",
            "score": int(round(factor_scores["money"])),
            "weight": weights["money"],
            "trend": _trend_from_late(late_row),
            "blurb": money_blurb,
        },
        {
            "id": "ie",
            "label": "IE pressure",
            "score": int(round(factor_scores["ie"])),
            "weight": weights["ie"],
            "trend": _ie_trend(late_row),
            "blurb": ie_blurb,
        },
        {
            "id": "ads",
            "label": "Ad surge",
            "score": int(round(ad_sc)),
            "weight": weights["ads"],
            "trend": _ad_trend(weekly_rows),
            "blurb": ad_surge_blurb(weekly_rows, int(round(ad_sc))),
        },
        {
            "id": "narrative",
            "label": "Narrative heat",
            "score": narr_score,
            "weight": weights["narrative"],
            "trend": "up" if narr_count >= 3 else "flat",
            "blurb": narrative_blurb(narr_count),
        },
    ]

    if poll_included:
        factors.append(
            {
                "id": "polls",
                "label": "Poll movement",
                "score": poll_score_display,
                "weight": weights["polls"],
                "trend": poll_trend,
                "blurb": poll_blurb,
            }
        )
    else:
        factors.append(
            {
                "id": "polls",
                "label": "Poll movement",
                "score": None,
                "weight": 0.0,
                "trend": "flat",
                "blurb": poll_blurb,
                "unavailable": True,
            }
        )

    return {
        "threatIndex": int(ti),
        "status": st,
        "factors": factors,
        "factor_scores": factor_scores,
        "weights_used": weights,
        "poll_included": poll_included,
    }


def _money_blurb(late_row: dict[str, Any] | None) -> str:
    if not late_row:
        return "Late-money window data missing."
    t = late_row.get("totals") or {}
    seven = t.get("seven_day")
    return f"7-day late contributions ${seven:,.0f} in FPPC 90-day window (CAL-ACCESS S497/S496 buckets)."


def _ie_blurb(late_row: dict[str, Any] | None) -> str:
    if not late_row:
        return "IE totals missing."
    t = late_row.get("totals") or {}
    return (
        f"7-day IE ${t.get('ie_seven_day', 0):,.0f}; "
        f"cycle oppose ${t.get('ie_oppose', 0):,.0f} vs support ${t.get('ie_support', 0):,.0f}."
    )


def _trend_from_late(late_row: dict[str, Any] | None) -> str:
    buckets = (late_row or {}).get("daily_buckets") or []
    if len(buckets) < 14:
        return "flat"
    recent = sum(float(b.get("amount") or 0) for b in buckets[-7:])
    prior = sum(float(b.get("amount") or 0) for b in buckets[-14:-7])
    if recent > prior * 1.1:
        return "up"
    if recent < prior * 0.9:
        return "down"
    return "flat"


def _ad_trend(weekly_rows: list[dict[str, Any]] | None) -> str:
    if not weekly_rows or len(weekly_rows) < 2:
        return "flat"
    ordered = sorted(weekly_rows, key=lambda r: r.get("week_start") or "")
    last = float(ordered[-1].get("spend_usd") or 0)
    prior = float(ordered[-2].get("spend_usd") or 0)
    if last > prior * 1.1:
        return "up"
    if last < prior * 0.9:
        return "down"
    return "flat"


def _ie_trend(late_row: dict[str, Any] | None) -> str:
    t = (late_row or {}).get("totals") or {}
    if float(t.get("ie_last_24h") or 0) > 0 or float(t.get("ie_seven_day") or 0) > 50000:
        return "up"
    return "flat"


def deltas_for_district(
    district_id: str,
    ti_today: int,
    snapshots: list[dict[str, Any]],
    today: dt.date,
) -> dict[str, Any]:
    def ti_on(target: dt.date) -> int | None:
        for snap in reversed(snapshots):
            if snap.get("date") == target.isoformat():
                row = (snap.get("districts") or {}).get(district_id)
                if row and row.get("threatIndex") is not None:
                    return int(row["threatIndex"])
        for snap in reversed(snapshots):
            sd = parse_date(snap.get("date"))
            if not sd or sd > target:
                continue
            if (target - sd).days <= 2:
                row = (snap.get("districts") or {}).get(district_id)
                if row and row.get("threatIndex") is not None:
                    return int(row["threatIndex"])
        return None

    first_date = snapshots[0]["date"] if snapshots else today.isoformat()
    d24 = None
    d7 = None
    yday = today - dt.timedelta(days=1)
    week = today - dt.timedelta(days=7)
    ti_y = ti_on(yday)
    ti_w = ti_on(week)
    if ti_y is not None:
        d24 = ti_today - ti_y
    if ti_w is not None:
        d7 = ti_today - ti_w

    history_note = None
    if d24 is None and d7 is None:
        history_note = f"History builds daily from {first_date}; 24h/7d change appears after the next refresh."

    return {
        "delta24h": d24,
        "delta7d": d7,
        "history_note": history_note,
        "history_started": first_date,
    }
