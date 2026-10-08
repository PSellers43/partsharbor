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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]  # assemblyedge/
AE_SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(AE_SCRIPTS))
from ie_direction import (  # noqa: E402
    classify_ie_row,
    excluded_target_names,
    ie_effect_on_r,
    party_for_target,
    roster_parties,
)

PT = ZoneInfo("America/Los_Angeles")
OFFICIAL_SOV = ROOT / "data" / "election-history" / "official" / "asm-2024-general-sov.json"
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
                ts_label = dt.astimezone(PT).strftime("%b %d · %I:%M%p PT")
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


def load_official_lean_map() -> dict[str, dict]:
    if not OFFICIAL_SOV.exists():
        return {}
    doc = load_json(OFFICIAL_SOV)
    src = doc.get("source") or {}
    as_of = doc.get("as_of_date") or ""
    label = src.get("label") or "CA SOS 2024 SOV"
    out: dict[str, dict] = {}
    for did, row in (doc.get("districts") or {}).items():
        if did not in BEACHHEAD_IDS:
            continue
        lean = row.get("lean") or "—"
        out[did] = {
            "lean": lean,
            "margin_r_pct": row.get("margin_r_pct"),
            "dem_votes": row.get("dem_votes"),
            "rep_votes": row.get("rep_votes"),
            "dem_pct": row.get("dem_pct"),
            "rep_pct": row.get("rep_pct"),
            "source_label": "SOS 2024 SOV",
            "source": label,
            "source_url": src.get("url"),
            "as_of_date": as_of,
            "context_2026": row.get("context_2026"),
        }
    return out


def format_money(n: float | None) -> str:
    if n is None:
        return "—"
    if abs(n) >= 1000:
        return f"${n:,.0f}"
    return f"${n:.0f}"


def build_rival(did: str, money_dist: dict | None, beach: dict | None) -> dict:
    roster_row = None
    if beach:
        for d in beach.get("districts") or []:
            if d.get("id") == did:
                roster_row = d
                break

    opponent_name = "—"
    opponent_party = "—"
    notes = "Public race context from SOS certified list + CAL-ACCESS committee match. Spend from filed totals."
    if roster_row and roster_row.get("open_seat"):
        gc = roster_row.get("general_candidates") or []
        r_c = next((p for p in gc if p.get("party") == "R"), None)
        d_c = next((p for p in gc if p.get("party") == "D"), None)
        if r_c and d_c:
            opponent_name = f"{r_c.get('name')} (R) vs {d_c.get('name')} (D)"
            opponent_party = "Open seat"
            notes = (roster_row.get("outgoing_note") or "") + " " + notes
        else:
            opponent_name = "Open seat — see certified list"
            opponent_party = "Open"
    elif roster_row and roster_row.get("known_opponents"):
        opp = roster_row["known_opponents"][0]
        opponent_name = opp.get("name") or opponent_name
        opponent_party = opp.get("party") or opponent_party

    if money_dist:
        for c in money_dist.get("candidates") or []:
            if c.get("role") == "Opponent" and c.get("name") and not (roster_row and roster_row.get("open_seat")):
                opponent_name = c["name"]
                opponent_party = c.get("party") or opponent_party

    parties_roster = roster_parties(roster_row, money_dist)
    excluded = excluded_target_names(roster_row)
    ie_anti_r: list[dict] = []
    ie_pro_r: list[dict] = []
    if money_dist:
        for ie in money_dist.get("ie") or []:
            side = (ie.get("side") or "").lower()
            targets = ie.get("targets") or []
            target = targets[0] if targets else "unknown"
            effect = classify_ie_row(side, target, parties_roster, excluded)
            if effect is None:
                continue
            spend = ie.get("spend")
            band = format_money(spend) + " filed spend" if spend else "—"
            tgt_party = party_for_target(target, parties_roster)
            if side == "support":
                role = f"Support {target}" + (f" ({tgt_party})" if tgt_party else "")
            else:
                role = f"Oppose {target}" + (f" ({tgt_party})" if tgt_party else "")
            if effect == "pro_r":
                role += " · helps R side"
            else:
                role += " · helps D / opposes R"
            entry = {"name": ie.get("name") or "IE committee", "role": role, "spendBand": band}
            if effect == "anti_r":
                ie_anti_r.append(entry)
            else:
                ie_pro_r.append(entry)
    ie_anti_r.sort(key=lambda x: x.get("spendBand", ""), reverse=True)
    ie_pro_r.sort(key=lambda x: x.get("spendBand", ""), reverse=True)
    return {
        "opponent": opponent_name,
        "party": opponent_party,
        "notes": notes.strip(),
        "open_seat": bool(roster_row and roster_row.get("open_seat")),
        "ieSupporters": ie_anti_r[:6],
        "ieAllies": ie_pro_r[:6],
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

    ie7_anti = float(t.get("ie_seven_day_anti_r") or 0)
    if ie7_anti >= 100000:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Anti-R IE activity (7-day window)",
                "detail": f"{code}: ${ie7_anti:,.0f} independent expenditures classified as anti-R in the latest 7 days.",
                "decision": "spend",
                "decisionLabel": "Consider spend",
            }
        )

    last_filed = float(t.get("last_filed_day") or t.get("last_24h") or 0)
    filed_label = t.get("last_filed_day_date") or as_of.isoformat()
    if last_filed >= 25000:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Late contributions (last filed day)",
                "detail": f"${last_filed:,.0f} in Form 497 activity on last filed day ({filed_label}).",
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

    as_of = parse_date(args.as_of) or datetime.now(PT).date()

    money = load_json(ROOT / "data" / "calaccess" / "latest" / "money-by-district.json")
    late = load_json(ROOT / "data" / "calaccess" / "latest" / "late-money-by-district.json")
    polling = load_json(ROOT / "data" / "polling" / "latest.json")
    beach = load_json(ROOT / "data" / "calaccess" / "beachheads.json")
    social = load_json(ROOT / "data" / "social" / "latest" / "social-feed.json")

    gap_days = int(polling.get("gap_recent_days") or 90)
    poll_by_id = {d["id"]: d for d in polling.get("districts") or []}

    lean_map = load_official_lean_map()

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
        lean_info = lean_map.get(did) or {"lean": "—", "source_label": "SOS 2024 SOV", "source": "Official SOV file missing"}

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
        "generated_at": datetime.now(PT).isoformat(),
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
                "path": "data/election-history/official/asm-2024-general-sov.json",
                "source_label": "SOS 2024 SOV",
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
