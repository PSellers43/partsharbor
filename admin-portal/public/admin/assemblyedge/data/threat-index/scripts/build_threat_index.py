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
TI_ROOT = ROOT / "data" / "threat-index"
LATEST = TI_ROOT / "latest"
SNAPSHOTS = TI_ROOT / "snapshots"
SCRIPTS = TI_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
from pt_dates import now_pt_iso, today_pt  # noqa: E402
from ti_ie_direction import (  # noqa: E402
    enrich_late_totals,
    ie_effect,
    is_ballot_target,
    target_party,
)
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
OFFICIAL_LEAN_PATH = ROOT / "data" / "election-history" / "official" / "asm-2024-general-sov.json"
PT = ZoneInfo("America/Los_Angeles")

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


def load_official_lean() -> dict[str, dict]:
    if not OFFICIAL_LEAN_PATH.exists():
        return {}
    doc = load_json(OFFICIAL_LEAN_PATH)
    threshold = float(doc.get("even_threshold_abs_margin_r_pct") or 1.0)
    src = doc.get("source_label") or "CA SOS SOV"
    url = doc.get("source_url")
    as_of = doc.get("as_of")
    out: dict[str, dict] = {}
    for did, row in (doc.get("districts") or {}).items():
        margin = float(row.get("margin_r_pct") or 0)
        if abs(margin) < threshold:
            lean = "Even"
        elif margin > 0:
            lean = f"R+{margin:.1f}"
        else:
            lean = f"D+{-margin:.1f}"
        out[did] = {
            "lean": lean,
            "margin_r_pct": margin,
            "dem_votes": row.get("dem_votes"),
            "rep_votes": row.get("rep_votes"),
            "source": "2024 Assembly result (SOS SOV)",
            "source_url": url,
            "official_as_of": as_of,
            "note_2026": row.get("note_2026"),
        }
    return out


def roster_for_district(beach: dict | None, did: str) -> dict | None:
    if not beach:
        return None
    for d in beach.get("districts") or []:
        if d.get("id") == did:
            return d
    return None


def late_row_with_ie_direction(late_row: dict | None, money_dist: dict | None, roster: dict | None) -> dict | None:
    if not late_row:
        return None
    merged = dict(late_row)
    totals = dict(late_row.get("totals") or {})
    totals.update(enrich_late_totals(late_row, money_dist, roster))
    merged["totals"] = totals
    return merged


def format_money(n: float | None) -> str:
    if n is None:
        return "—"
    if abs(n) >= 1000:
        return f"${n:,.0f}"
    return f"${n:.0f}"


def _ie_role_label(effect: str, target: str, roster: dict | None) -> str:
    party = target_party(target, roster) or "?"
    if effect == "anti_r":
        return f"Anti-Republican (support D or oppose R) · target {target} ({party})"
    if effect == "pro_r":
        return f"Pro-Republican (support R or oppose D) · target {target} ({party})"
    return f"IE · target {target}"


def build_rival(did: str, money_dist: dict | None, beach: dict | None) -> dict:
    roster = roster_for_district(beach, did)
    opponent_name = "—"
    opponent_party = "—"
    race_label = None
    if roster and roster.get("open_seat"):
        gc = roster.get("general_candidates") or []
        r_c = next((c for c in gc if c.get("party") == "R"), None)
        d_c = next((c for c in gc if c.get("party") == "D"), None)
        if r_c and d_c:
            opponent_name = f"{r_c.get('name')} (R) vs {d_c.get('name')} (D)"
            opponent_party = "Open seat"
            race_label = opponent_name
        if roster.get("outgoing_note"):
            race_label = (race_label or "Open seat") + " · " + roster["outgoing_note"]
    elif roster:
        inc = roster.get("incumbent") or {}
        if roster.get("known_opponents"):
            opp = roster["known_opponents"][0]
            opponent_name = opp.get("name") or opponent_name
            opponent_party = opp.get("party") or opponent_party
        if inc.get("name"):
            race_label = f"{inc.get('name')} ({inc.get('party')}) incumbent vs {opponent_name} ({opponent_party})"

    notes = "SOS certified 2026 roster + CAL-ACCESS Form 496/465 totals. IE side from target candidate party + support/oppose code."
    ie_anti_r: list[dict] = []
    ie_pro_r: list[dict] = []
    if money_dist:
        for c in money_dist.get("candidates") or []:
            if c.get("role") == "Opponent" and c.get("name") and not (roster and roster.get("open_seat")):
                opponent_name = c["name"]
                opponent_party = c.get("party") or opponent_party
        for ie in money_dist.get("ie") or []:
            targets = ie.get("targets") or []
            if not targets:
                continue
            target = str(targets[0])
            if not is_ballot_target(target, roster):
                continue
            effect = ie_effect(ie.get("side") or "", target, roster)
            if not effect:
                continue
            spend = ie.get("spend")
            band = format_money(spend) + " filed spend" if spend else "—"
            entry = {
                "name": ie.get("name") or "IE committee",
                "role": _ie_role_label(effect, target, roster),
                "spendBand": band,
            }
            if effect == "anti_r":
                ie_anti_r.append(entry)
            else:
                ie_pro_r.append(entry)
    ie_anti_r.sort(key=lambda x: x.get("spendBand", ""), reverse=True)
    ie_pro_r.sort(key=lambda x: x.get("spendBand", ""), reverse=True)
    return {
        "opponent": opponent_name,
        "party": opponent_party,
        "race_label": race_label,
        "notes": notes,
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

    ie7 = float(t.get("ie_seven_day") or 0)
    anti7 = float(t.get("ie_anti_r_period") or 0)
    if anti7 >= 100000:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Anti-Republican IE in 7-day window",
                "detail": f"{code}: ${anti7:,.0f} direction-aware anti-R IE in the latest 7 days (${ie7:,.0f} total IE).",
                "decision": "spend",
                "decisionLabel": "Consider spend",
            }
        )

    last_day = float(t.get("last_filed_day") or t.get("last_24h") or 0)
    filed_label = t.get("last_filed_day_date") or as_of.isoformat()
    if last_day >= 25000:
        alerts.append(
            {
                "ts": as_of.isoformat(),
                "title": "Late contributions on last filed day",
                "detail": f"${last_day:,.0f} in Form 497 activity on last filed day ({filed_label}) in the export.",
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

    as_of = parse_date(args.as_of) or today_pt()

    money = load_json(ROOT / "data" / "calaccess" / "latest" / "money-by-district.json")
    late = load_json(ROOT / "data" / "calaccess" / "latest" / "late-money-by-district.json")
    polling = load_json(ROOT / "data" / "polling" / "latest.json")
    beach = load_json(ROOT / "data" / "calaccess" / "beachheads.json")
    social = load_json(ROOT / "data" / "social" / "latest" / "social-feed.json")

    gap_days = int(polling.get("gap_recent_days") or 90)
    poll_by_id = {d["id"]: d for d in polling.get("districts") or []}

    lean_map = load_official_lean()

    prev_latest = LATEST / "threat-index-by-district.json"
    prev_news: dict[str, list] = {}
    if args.skip_news and prev_latest.exists():
        prev_news = (load_json(prev_latest).get("narrative") or {})

    news_by_id: dict[str, list] = {}
    news_fetched_at = now_pt_iso()
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

    money_raw = {}
    ie_raw = {}
    for did in BEACHHEAD_IDS:
        roster = roster_for_district(beach, did)
        money_dist = (money.get("districts") or {}).get(did)
        late_enriched = late_row_with_ie_direction((late.get("districts") or {}).get(did), money_dist, roster)
        money_raw[did] = money_velocity_raw(late_enriched)
        ie_raw[did] = ie_pressure_raw(late_enriched)
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
        roster = roster_for_district(beach, did)
        money_dist = (money.get("districts") or {}).get(did)
        late_row = late_row_with_ie_direction((late.get("districts") or {}).get(did), money_dist, roster)
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
        lean_info = lean_map.get(did) or {"lean": "—", "source": "Official 2024 SOS lean unavailable"}

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
        rival_out[did] = build_rival(did, money_dist, beach)
        alerts_out[did] = build_alerts(
            did, code, late_row, narrative_out[did], ti_block["threatIndex"], ti_block["status"], posts, as_of
        )

    payload = {
        "schema_version": 1,
        "product": "MajorityIQ",
        "generated_at": now_pt_iso(),
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
                "source": "2024 Assembly result (SOS SOV)",
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
