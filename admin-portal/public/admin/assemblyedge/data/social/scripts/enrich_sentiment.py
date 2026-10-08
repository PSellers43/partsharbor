#!/usr/bin/env python3
"""Deterministic sentiment from public post text (lexicon + optional flags).

Runs offline in push-social-feed.sh — no paid API. Scores are labeled in the UI as
tone estimates (not polling). Flags nudge but do not replace text scoring.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FEED_PATH = ROOT / "latest" / "social-feed.json"
TZ = ZoneInfo("America/Los_Angeles")
MAX_HISTORY_DAYS = 120
MIN_NET_SAMPLES = 1

# Compact campaign lexicon (deterministic, English + common political cues).
POSITIVE = {
    "thank",
    "thanks",
    "grateful",
    "honored",
    "proud",
    "excited",
    "celebrate",
    "endorse",
    "endorsement",
    "support",
    "supporter",
    "together",
    "community",
    "volunteer",
    "canvass",
    "town hall",
    "great",
    "fantastic",
    "win",
    "victory",
    "strong",
    "leadership",
    "freedom",
    "opportunity",
    "record",
    "bipartisan",
}
NEGATIVE = {
    "attack",
    "lie",
    "lies",
    "lying",
    "corrupt",
    "corruption",
    "failed",
    "failure",
    "disaster",
    "dangerous",
    "radical",
    "extreme",
    "soft",
    "crime",
    "crisis",
    "tax",
    "taxes",
    "inflation",
    "border",
    "illegal",
    "shame",
    "shameful",
    "betray",
    "betrayal",
    "hypocrisy",
    "hypocrite",
    "out of touch",
    "recall",
    "impeach",
    "against",
    "oppose",
    "opposed",
    "stop",
    "reject",
    "defeat",
    "worst",
    "broken",
    "fraud",
}

FLAG_NUDGE = {
    "attack": -0.35,
    "ad": 0.08,
    "endorsement": 0.25,
    "spike": 0.0,
    "event": 0.12,
    "policy": 0.05,
    "fundraising": 0.03,
}


def normalize_text(post: dict) -> str:
    chunks = [
        post.get("text") or "",
        post.get("summary") or "",
        post.get("title") or "",
    ]
    raw = " ".join(c for c in chunks if c).lower()
    raw = re.sub(r"https?://\S+", " ", raw)
    raw = re.sub(r"@[\w_]+", " ", raw)
    raw = re.sub(r"[^a-z0-9\s'-]", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def lexicon_score(text: str) -> tuple[float | None, str | None]:
    if not text or len(text) < 8:
        return None, None
    tokens = set(text.split())
    pos = sum(1 for w in POSITIVE if w in tokens or w in text)
    neg = sum(1 for w in NEGATIVE if w in tokens or w in text)
    if pos == 0 and neg == 0:
        return None, None
    raw = (pos - neg) / max(3, pos + neg)
    score = max(-1.0, min(1.0, round(raw * 0.85, 3)))
    if score > 0.12:
        label = "positive"
    elif score < -0.12:
        label = "negative"
    else:
        label = "neutral"
    return score, label


def score_post(post: dict) -> tuple[float | None, str | None]:
    text = normalize_text(post)
    score, label = lexicon_score(text)
    nudge = 0.0
    for f in post.get("flags") or []:
        nudge += FLAG_NUDGE.get(f, 0.0)
    if score is None and nudge == 0.0:
        return None, None
    if score is None:
        score = max(-1.0, min(1.0, round(nudge, 3)))
    else:
        score = max(-1.0, min(1.0, round(score + nudge * 0.35, 3)))
    if label is None:
        if score > 0.12:
            label = "positive"
        elif score < -0.12:
            label = "negative"
        else:
            label = "neutral"
    return score, label


def pacific_date(iso: str) -> str | None:
    if not iso:
        return None
    try:
        if len(iso) == 10:
            return iso
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ).date().isoformat()
    except ValueError:
        return None


def round_avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def bucket(values: list[float]) -> dict:
    n = len(values)
    return {"avg": round_avg(values), "n": n}


def side_from_party(party: str | None) -> str | None:
    if not party:
        return None
    p = party.strip().upper()
    if p == "R":
        return "toward_r"
    if p == "D":
        return "toward_d"
    return None


def sides_from_mention(item: dict) -> list[str]:
    sides: set[str] = set()
    party_side = side_from_party(item.get("party"))
    if party_side:
        sides.add(party_side)
    cand = (item.get("candidate") or "").lower()
    if "gonzalez" in cand or "hoover" in cand or "murphy" in cand or "wallis" in cand:
        sides.add("toward_r")
    if "obeso" in cand or "slavensky" in cand or "pacheco" in cand or "cervantes" in cand or "farias" in cand or "namvar" in cand:
        sides.add("toward_d")
    if "castillo" in cand:
        sides.add("toward_r")
    if "davies" in cand:
        sides.add("toward_r")
    return list(sides)


def apply_post_sentiment(post: dict) -> None:
    score, label = score_post(post)
    if score is None:
        post.pop("sentiment", None)
        post.pop("sentiment_label", None)
        post["sentiment_method"] = "lexicon_unscored"
        return
    post["sentiment"] = score
    post["sentiment_label"] = label
    post["sentiment_method"] = "lexicon"


def build_history(feed: dict) -> list[dict]:
    by_day: dict[tuple[str, str], dict] = {}

    def ensure(date: str, district: str) -> dict:
        key = (date, district)
        if key not in by_day:
            by_day[key] = {
                "date": date,
                "district": district,
                "_candidate": [],
                "_mentions": [],
                "_toward_r": [],
                "_toward_d": [],
            }
        return by_day[key]

    for code, block in (feed.get("districts") or {}).items():
        for post in block.get("posts") or []:
            apply_post_sentiment(post)
            score = post.get("sentiment")
            if score is None:
                continue
            day = pacific_date(post.get("created_at") or "")
            if not day:
                continue
            row = ensure(day, code)
            row["_candidate"].append(float(score))
            side = side_from_party(post.get("party"))
            if side == "toward_r":
                row["_toward_r"].append(float(score))
            elif side == "toward_d":
                row["_toward_d"].append(float(score))

    for mention in feed.get("mentions") or []:
        apply_post_sentiment(mention)
        score = mention.get("sentiment")
        if score is None:
            continue
        district = mention.get("district")
        day = pacific_date(mention.get("created_at") or "")
        if not district or not day:
            continue
        row = ensure(day, district)
        row["_mentions"].append(float(score))
        for side in sides_from_mention(mention):
            if side == "toward_r":
                row["_toward_r"].append(float(score))
            elif side == "toward_d":
                row["_toward_d"].append(float(score))

    out: list[dict] = []
    for row in by_day.values():
        toward_r = bucket(row["_toward_r"])
        toward_d = bucket(row["_toward_d"])
        net = None
        if toward_r["n"] >= MIN_NET_SAMPLES and toward_d["n"] >= MIN_NET_SAMPLES:
            if toward_r["avg"] is not None and toward_d["avg"] is not None:
                net = round(toward_r["avg"] - toward_d["avg"], 3)
        elif toward_r["n"] >= MIN_NET_SAMPLES and toward_r["avg"] is not None:
            net = toward_r["avg"]
        elif toward_d["n"] >= MIN_NET_SAMPLES and toward_d["avg"] is not None:
            net = -toward_d["avg"]

        out.append(
            {
                "date": row["date"],
                "district": row["district"],
                "candidate_posts": bucket(row["_candidate"]),
                "mentions": bucket(row["_mentions"]),
                "toward_r": toward_r,
                "toward_d": toward_d,
                "net": net,
            }
        )

    out.sort(key=lambda r: (r["date"], r["district"]))
    if len(out) > MAX_HISTORY_DAYS * 6:
        dates = sorted({r["date"] for r in out})
        keep = set(dates[-MAX_HISTORY_DAYS:])
        out = [r for r in out if r["date"] in keep]
    return out


def merge_history(existing: list[dict] | None, computed: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for row in existing or []:
        merged[(row["date"], row["district"])] = row
    for row in computed:
        merged[(row["date"], row["district"])] = row
    out = list(merged.values())
    out.sort(key=lambda r: (r["date"], r["district"]))
    dates = sorted({r["date"] for r in out})
    if len(dates) > MAX_HISTORY_DAYS:
        keep = set(dates[-MAX_HISTORY_DAYS:])
        out = [r for r in out if r["date"] in keep]
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FEED_PATH
    feed = json.loads(path.read_text(encoding="utf-8"))
    computed = build_history(feed)
    feed["sentiment_history"] = merge_history(feed.get("sentiment_history"), computed)
    feed["sentiment_scoring"] = {
        "method": "lexicon",
        "label": "Tone est. from post text (deterministic lexicon; not polling)",
    }
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    scored = sum(
        1
        for block in (feed.get("districts") or {}).values()
        for p in block.get("posts") or []
        if p.get("sentiment") is not None
    )
    print(f"Wrote {path} · history rows {len(feed['sentiment_history'])} · scored posts {scored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
