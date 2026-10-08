#!/usr/bin/env python3
"""Build Threat Index, news, rival, alerts JSON for all beachhead districts."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # assemblyedge/
TI_ROOT = ROOT / "data" / "threat-index"
LATEST = TI_ROOT / "latest"
SNAPSHOTS = TI_ROOT / "snapshots"
SCRIPTS = TI_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
from ti_compute import (  # noqa: E402
    compute_district_ti,
    deltas_for_district,
    ie_pressure_raw,
    money_velocity_raw,
    narrative_raw,
    normalize_across,
    parse_date,
    poll_is_recent,
)

BEACHHEAD_IDS = ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"]

NEWS_QUERIES = {
    "ad-7": "California Assembly District 7 Sacramento Hoover election 2026",
    "ad-27": "California Assembly District 27 Fresno Murphy Pacheco 2026",
    "ad-36": "California Assembly District 36 Imperial Coachella Gonzalez 2026",
    "ad-47": "California Assembly District 47 Wallis Namvar Coachella 2026",
    "ad-58": "California Assembly District 58 Castillo Cervantes Riverside 2026",
    "ad-74": "California Assembly District 74 Laurie Davies Farias Orange 2026",
}


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_google_news_rss(query: str, max_items: int = 12) -> list[dict]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "MajorityIQ-build/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall(".//item")[:max_items]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate")
        pub_date = None
        ts_label = pub or ""
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
                pub_date = dt.date().isoformat()
                ts_label = dt.astimezone(timezone.utc).strftime("%b %d · %I:%M%p UTC")
            except (TypeError, ValueError, OSError):
                pass
        outlet = title.split(" - ")[-1].strip() if " - " in title else "Google News"
        clean_title = title.rsplit(" - ", 1)[0] if " - " in title else title
        items.append(
            {
                "outlet": outlet,
                "title": clean_title,
                "ts": ts_label,
                "pub_date": pub_date,
                "sentiment": "watch" if re.search(r"spend|attack|heat|tight|toss", clean_title, re.I) else "neutral",
                "url": link or "https://news.google.com/",
            }
        )
    return items


def compute_lean_from_geojson() -> dict[str, dict]:
    eh = ROOT / "data" / "election-history" / "latest"
    out = {}
    for did in BEACHHEAD_IDS:
        path = eh / f"{did}-precincts.geojson"
        if not path.exists():
            continue
        g = load_json(path)
        dem_v = rep_v = 0.0
        prec_with = 0
        for feat in g.get("features") or []:
            g24 = (feat.get("properties") or {}).get("g24_asm")
            if not g24:
                continue
            v = float(g24.get("votes_two_party") or 0)
            if v <= 0:
                continue
            dem_pct = g24.get("dem_pct")
            if dem_pct is None:
                continue
            dem_v += v * float(dem_pct) / 100.0
            rep_v += v * (100.0 - float(dem_pct)) / 100.0
            prec_with += 1
        tot = dem_v + rep_v
        if tot <= 0:
            out[did] = {"lean": "—", "source": "SWDB 2024 precinct roll-up (no votes in bundle)"}
            continue
        margin_r = rep_v / tot * 100.0 - dem_v / tot * 100.0
        if abs(margin_r) < 1.0:
            lean = "Even"
        elif margin_r > 0:
            lean = f"R+{margin_r:.1f}"
        else:
            lean = f"D+{-margin_r:.1f}"
        out[did] = {
            "lean": lean,
            "margin_r_pct": round(margin_r, 2),
            "votes_two_party": int(tot),
            "precincts_with_g24": prec_with,
            "source": "SWDB 2024 general Assembly (precinct roll-up in election-history GeoJSON)",
        }
    return out


def format_money(n: float | None) -> str:
    if n is None:
        return "—"
    if abs(n) >= 1000:
        return f"${n:,.0f}"
    return f"${n:.0f}"


def build_rival(did: str, money_dist: dict | None, beach: dict | None) -> dict:
    roster = None
    if beach:
        for d in beach.get("districts") or []:
            if d.get("id") == did:
                roster = d
                break
    opponent_name = "Opponent (see CAL-ACCESS match)"
    opponent_party = "—"
    if roster and roster.get("known_opponents"):
        opp = roster["known_opponents"][0]
        opponent_name = opp.get("name") or opponent_name
        opponent_party = opp.get("party") or opponent_party
    notes = "Public race context from SOS certified list + CAL-ACCESS committee match. Spend from filed totals."
    ie_supporters: list[dict] = []
    ie_allies: list[dict] = []
    if money_dist:
        for c in money_dist.get("candidates") or []:
            if c.get("role") == "Opponent" and c.get("name"):
                opponent_name = c["name"]
        for ie in money_dist.get("ie") or []:
            side = (ie.get("side") or "").lower()
            spend = ie.get("spend")
            band = format_money(spend) + " filed spend" if spend else "—"
            entry = {
                "name": ie.get("name") or "IE committee",
                "role": "Oppose incumbent / support challenger" if side == "oppose" else "Support incumbent",
                "spendBand": band,
            }
            if side == "oppose":
                ie_supporters.append(entry)
            else:
                ie_allies.append(entry)
    ie_supporters.sort(key=lambda x: x.get("spendBand", ""), reverse=True)
    ie_allies.sort(key=lambda x: x.get("spendBand", ""), reverse=True)
    return {
        "opponent": opponent_name,
        "party": opponent_party,
        "notes": notes,
        "ieSupporters": ie_supporters[:6],
        "ieAllies": ie_allies[:6],
    }


def build_alerts(
    did: str,
    code: str,
    late_row: dict | None,
    news: list[dict],
    ti: int,
    status: str,
    social_posts: list[dict],
    as_of: date,
) -> list[dict]:
    alerts: list[dict] = []
    t = (late_row or {}).get("totals") or {}

    ie7 = float(t.get("ie_seven_day") or 0)
    if ie7 >= 100000:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "IE activity in 7-day window",
                "detail": f"{code}: ${ie7:,.0f} independent expenditures in the latest 7 days (CAL-ACCESS late-money ingest).",
                "decision": "spend",
                "decisionLabel": "Consider spend",
            }
        )

    last24 = float(t.get("last_24h") or 0)
    if last24 >= 25000:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Late contribution filings (24h)",
                "detail": f"${last24:,.0f} in Form 497/496 activity in the last 24h vs export as-of.",
                "decision": "hold",
                "decisionLabel": "Hold & monitor",
            }
        )

    recent_news = [n for n in news if parse_date(n.get("pub_date")) and (as_of - parse_date(n.get("pub_date"))).days <= 2]
    if len(recent_news) >= 2:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Narrative cluster (48h)",
                "detail": f"{len(recent_news)} race-relevant headlines in 48h — scan News tab for links.",
                "decision": "message",
                "decisionLabel": "Message check",
            }
        )

    attacks = [
        p
        for p in social_posts
        if (p.get("tag") or "").lower() == "attack"
        or "attack" in [f.lower() for f in (p.get("flags") or [])]
    ]
    if attacks:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Notable social posts (attack-tagged)",
                "detail": f"{len(attacks)} attack-tagged post(s) in latest X digest for {code}.",
                "decision": "message",
                "decisionLabel": "Message check",
            }
        )

    if status == "elevated":
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": f"Threat Index {ti} — Elevated",
                "detail": "Composite crossed the Elevated threshold (≥65) from live money, IE, news, and polling inputs.",
                "decision": "spend",
                "decisionLabel": "Consider spend",
            }
        )

    if not alerts:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "No high-severity rule triggers",
                "detail": "Routine monitoring — review Money and late-money tabs on filing days.",
                "decision": "hold",
                "decisionLabel": "Hold & monitor",
            }
        )
    return alerts[:8]


def load_snapshots() -> list[dict]:
    snaps = []
    if not SNAPSHOTS.exists():
        return snaps
    for p in sorted(SNAPSHOTS.glob("threat-index-*.json")):
        try:
            snaps.append(load_json(p))
        except json.JSONDecodeError:
            continue
    snaps.sort(key=lambda s: s.get("date") or "")
    return snaps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-news", action="store_true", help="Reuse news from latest bundle")
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: UTC today)")
    args = parser.parse_args()

    as_of = parse_date(args.as_of) or datetime.now(timezone.utc).date()

    money = load_json(ROOT / "data" / "calaccess" / "latest" / "money-by-district.json")
    late = load_json(ROOT / "data" / "calaccess" / "latest" / "late-money-by-district.json")
    polling = load_json(ROOT / "data" / "polling" / "latest.json")
    beach = load_json(ROOT / "data" / "calaccess" / "beachheads.json")
    social = load_json(ROOT / "data" / "social" / "latest" / "social-feed.json")

    gap_days = int(polling.get("gap_recent_days") or 90)
    poll_by_id = {d["id"]: d for d in polling.get("districts") or []}

    lean_map = compute_lean_from_geojson()

    prev_latest = LATEST / "threat-index-by-district.json"
    prev_news: dict[str, list] = {}
    if args.skip_news and prev_latest.exists():
        prev_news = (load_json(prev_latest).get("narrative") or {})

    news_by_id: dict[str, list] = {}
    news_fetched_at = datetime.now(timezone.utc).isoformat()
    for did in BEACHHEAD_IDS:
        if args.skip_news and did in prev_news:
            news_by_id[did] = prev_news[did]
            continue
        try:
            news_by_id[did] = fetch_google_news_rss(NEWS_QUERIES[did])
            print(f"News {did}: {len(news_by_id[did])} items", file=sys.stderr)
        except Exception as exc:
            print(f"News fetch failed {did}: {exc}", file=sys.stderr)
            news_by_id[did] = prev_news.get(did, [])

    money_raw = {did: money_velocity_raw((late.get("districts") or {}).get(did)) for did in BEACHHEAD_IDS}
    ie_raw = {did: ie_pressure_raw((late.get("districts") or {}).get(did)) for did in BEACHHEAD_IDS}
    money_scores = normalize_across(money_raw)
    ie_scores = normalize_across(ie_raw)

    snapshots = load_snapshots()

    districts_out: dict[str, dict] = {}
    narrative_out: dict[str, list] = {}
    rival_out: dict[str, dict] = {}
    alerts_out: dict[str, list] = {}

    social_districts = (social.get("districts") or {}) if isinstance(social.get("districts"), dict) else {}
    if not social_districts:
        for row in social.get("districts") or []:
            if isinstance(row, dict) and row.get("id"):
                social_districts[row["id"]] = row

    for did in BEACHHEAD_IDS:
        late_row = (late.get("districts") or {}).get(did)
        poll_row = poll_by_id.get(did)
        ti_block = compute_district_ti(
            did,
            late_row,
            poll_row,
            news_by_id.get(did) or [],
            as_of,
            gap_days,
            money_scores=money_scores,
            ie_scores=ie_scores,
        )
        deltas = deltas_for_district(did, ti_block["threatIndex"], snapshots, as_of)
        lean_info = lean_map.get(did) or {"lean": "—", "source": "SWDB roll-up unavailable"}

        code = did.upper().replace("AD-", "AD-")
        if did.startswith("ad-"):
            code = "AD-" + did.split("-")[1]

        posts = []
        srow = social_districts.get(code) or social_districts.get(did)
        if isinstance(srow, dict):
            posts = srow.get("posts") or []

        districts_out[did] = {
            "id": did,
            "code": code,
            "threatIndex": ti_block["threatIndex"],
            "status": ti_block["status"],
            "delta24h": deltas["delta24h"],
            "delta7d": deltas["delta7d"],
            "history_note": deltas.get("history_note"),
            "lean": lean_info.get("lean"),
            "lean_meta": lean_info,
            "factors": ti_block["factors"],
        }
        narrative_out[did] = news_by_id.get(did) or []
        money_dist = (money.get("districts") or {}).get(did)
        rival_out[did] = build_rival(did, money_dist, beach)
        alerts_out[did] = build_alerts(
            did, code, late_row, narrative_out[did], ti_block["threatIndex"], ti_block["status"], posts, as_of
        )

    payload = {
        "schema_version": 1,
        "product": "MajorityIQ",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of.isoformat(),
        "formula": {
            "description": "Weighted composite 0–100 of money velocity, IE pressure, and narrative heat; poll movement included only when a public horse-race poll falls in the gap window. Ad surge excluded (no free source).",
            "base_weights": {"money": 0.3125, "ie": 0.25, "narrative": 0.25, "polls": 0.1875},
            "poll_exclusion": "When no recent poll: poll factor excluded and money/IE/narrative weights renormalized to sum to 1.",
            "narrative_rule": "score = min(100, 20 × headlines in last 7 days from build-time Google News RSS); 0 headlines → 0.",
            "status_thresholds": {"elevated": 65, "watch": 45},
            "normalization": "Money and IE ranked across the six beachheads (min-max ~18–95). Narrative uses the fixed headline rule above.",
        },
        "inputs": {
            "money_late": {
                "path": "data/calaccess/latest/late-money-by-district.json",
                "data_as_of": late.get("data_as_of"),
            },
            "money_cycle": {
                "path": "data/calaccess/latest/money-by-district.json",
                "data_as_of": money.get("data_as_of"),
            },
            "polling": {
                "path": "data/polling/latest.json",
                "updated_at": polling.get("updated_at"),
            },
            "news": {
                "source": "Google News RSS (build-time fetch)",
                "fetched_at": news_fetched_at,
            },
            "lean": {
                "source": "SWDB 2024 Assembly precinct roll-up (election-history GeoJSON)",
            },
        },
        "districts": districts_out,
        "narrative": narrative_out,
        "rival": rival_out,
        "alerts": alerts_out,
        "ads_unavailable": {
            "message": "No free, reliable Meta/Google political ad feed confirmed for CA Assembly races. Ads tab shows this state for all districts.",
        },
    }

    LATEST.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)

    snap_path = SNAPSHOTS / f"threat-index-{as_of.isoformat()}.json"
    snap_payload = {
        "date": as_of.isoformat(),
        "districts": {did: {"threatIndex": districts_out[did]["threatIndex"]} for did in BEACHHEAD_IDS},
    }
    snap_path.write_text(json.dumps(snap_payload, indent=2) + "\n", encoding="utf-8")

    latest_path = LATEST / "threat-index-by-district.json"
    dated_path = LATEST / f"threat-index-by-district-{as_of.isoformat()}.json"
    text = json.dumps(payload, indent=2) + "\n"
    latest_path.write_text(text, encoding="utf-8")
    dated_path.write_text(text, encoding="utf-8")
    print(f"Wrote {latest_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
