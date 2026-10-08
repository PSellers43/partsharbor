#!/usr/bin/env python3
"""
Build MajorityIQ Google political ads JSON from the free transparency bundle.

Source (no auth):
  https://storage.googleapis.com/political-csv/google-political-ads-transparency-bundle.zip

Raw ZIP stays in data/ads/offline/ (gitignored). Only data/ads/latest/ads-by-district.json is committed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile

csv.field_size_limit(min(sys.maxsize, 10_000_000))
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]  # data/ads/
AE_ROOT = ROOT.parent.parent  # assemblyedge/
OFFLINE = ROOT / "offline"
LATEST = ROOT / "latest"
BEACHHEADS = AE_ROOT / "data" / "calaccess" / "beachheads.json"
MONEY = AE_ROOT / "data" / "calaccess" / "latest" / "money-by-district.json"

BUNDLE_URL = "https://storage.googleapis.com/political-csv/google-political-ads-transparency-bundle.zip"
BUNDLE_NAME = "google-political-ads-transparency-bundle.zip"

WEEKLY_CSV = "google-political-ads-advertiser-weekly-spend.csv"
STATS_CSV = "google-political-ads-advertiser-stats.csv"
UPDATED_CSV = "google-political-ads-updated.csv"
CREATIVE_CSV = "google-political-ads-creative-stats.csv"

BEACHHEAD_IDS = ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"]

# Hand-curated Google advertiser names tied to public IE/candidate context (not invented spend).
EXTRA_NAME_MATCHES: dict[str, list[tuple[str, str]]] = {
    "ad-7": [("LEGISLATIVE ACTION VICTORY PAC", "IE"), ("LEGISLATIVE ACTION PAC", "IE")],
    "ad-36": [("GROW CALIFORNIA", "IE")],
}
TRANSPARENCY_BASE = "https://adstransparency.google.com/advertiser/{advertiser_id}?region=US"

DISTRICT_GEO_RE: dict[str, re.Pattern] = {
    did: re.compile(
        rf"(?i)(assembly\s+district\s*#?\s*{num}\b|state\s+assembly\s+district\s*#?\s*{num}\b|"
        rf"\bAD[- ]?{num}\b|\bASM\.?\s*{num}\b)",
    )
    for did, num in [
        ("ad-7", "7"),
        ("ad-27", "27"),
        ("ad-36", "36"),
        ("ad-47", "47"),
        ("ad-58", "58"),
        ("ad-74", "74"),
    ]
}


def log(msg: str) -> None:
    print(msg, flush=True)


def norm_name(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def download_bundle(force: bool = False) -> Path:
    OFFLINE.mkdir(parents=True, exist_ok=True)
    dest = OFFLINE / BUNDLE_NAME
    if dest.exists() and dest.stat().st_size > 50_000_000 and not force:
        log(f"[skip] bundle present ({dest.stat().st_size:,} bytes)")
        return dest
    log(f"[download] {BUNDLE_URL}")
    tmp = dest.with_suffix(".partial")
    urlretrieve(BUNDLE_URL, tmp)
    tmp.replace(dest)
    log(f"[ok] {dest.stat().st_size:,} bytes")
    return dest


def read_updated_time(zf: zipfile.ZipFile) -> str | None:
    try:
        with zf.open(UPDATED_CSV) as f:
            lines = f.read().decode("utf-8", errors="replace").strip().splitlines()
        if len(lines) >= 2:
            return lines[1].strip()
    except KeyError:
        pass
    return None


def district_people(beach: dict) -> dict[str, list[dict]]:
    """district_id -> [{name, party, patterns, side}]"""
    out: dict[str, list[dict]] = {did: [] for did in BEACHHEAD_IDS}
    for d in beach.get("districts") or []:
        did = d["id"]
        if d.get("open_seat"):
            for c in d.get("general_candidates") or []:
                out[did].append(
                    {
                        "name": c["name"],
                        "party": c.get("party"),
                        "committee_patterns": list(c.get("committee_patterns") or []),
                        "name_patterns": list(c.get("name_patterns") or []),
                        "side": c.get("party"),
                    }
                )
        else:
            inc = d.get("incumbent") or {}
            out[did].append(
                {
                    "name": inc["name"],
                    "party": inc.get("party"),
                    "committee_patterns": list(inc.get("committee_patterns") or []),
                    "name_patterns": list(inc.get("name_patterns") or []),
                    "side": inc.get("party"),
                }
            )
            for opp in d.get("known_opponents") or []:
                out[did].append(
                    {
                        "name": opp["name"],
                        "party": opp.get("party"),
                        "committee_patterns": list(opp.get("committee_patterns") or []),
                        "name_patterns": list(opp.get("name_patterns") or []),
                        "side": opp.get("party"),
                    }
                )
    return out


def ie_name_patterns(money: dict | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {did: [] for did in BEACHHEAD_IDS}
    if not money:
        return out
    for did in BEACHHEAD_IDS:
        dist = (money.get("districts") or {}).get(did) or {}
        for ie in dist.get("ie") or []:
            nm = ie.get("name") or ""
            if nm:
                out[did].append(norm_name(nm))
    return out


def name_matches_advertiser(
    patterns: Iterable[str],
    advertiser_name: str,
    *,
    require_assembly: bool = False,
) -> bool:
    an = norm_name(advertiser_name)
    if not an:
        return False
    if require_assembly and "ASSEMBLY" not in an:
        return False
    if "INSTITUTION" in an and "FOR ASSEMBLY" not in an:
        return False
    for p in patterns:
        pn = norm_name(p)
        if not pn:
            continue
        if "FOR ASSEMBLY" in pn or "ASSEMBLY 202" in pn:
            if pn in an or an in pn:
                return True
            continue
        # Surname-only tokens are not matched in fallback mode (avoid wrong "Name Surname for Assembly").
        if require_assembly and len(pn.split()) == 1:
            continue
        if len(pn.split()) == 1 and len(pn) >= 4:
            if pn in an and "ASSEMBLY" in an:
                return True
            continue
        if pn in an or an in pn:
            return True
        ptoks = set(pn.split())
        if len(ptoks) >= 3 and ptoks.issubset(set(an.split())):
            return True
    return False


def ie_matches_advertiser(ie_norm: str, advertiser_name: str) -> bool:
    """Conservative: CAL-ACCESS IE label must closely match Google advertiser name."""
    an = norm_name(advertiser_name)
    if not an or not ie_norm:
        return False
    if ie_norm == an:
        return True
    shorter, longer = (ie_norm, an) if len(ie_norm) <= len(an) else (an, ie_norm)
    if len(shorter) < 20:
        return shorter in longer
    if shorter in longer:
        return True
    # Allow minor truncation on long CAL-ACCESS names (ellipsis in export)
    if ie_norm.startswith(an[:40]) or an.startswith(ie_norm[:40]):
        return len(an) >= 20 and len(ie_norm) >= 20
    return False


def assign_district_by_name(
    advertiser_name: str,
    people_by_dist: dict[str, list[dict]],
    ie_patterns: dict[str, list[str]],
) -> list[tuple[str, str, str]]:
    """Returns list of (district_id, side, match_reason)."""
    hits: list[tuple[str, str, str]] = []
    for did, people in people_by_dist.items():
        for person in people:
            committee_pats = person.get("committee_patterns") or []
            if committee_pats and name_matches_advertiser(committee_pats, advertiser_name):
                hits.append((did, person.get("side") or "other", "advertiser_name"))
                break
            fallback = [person["name"]] + list(person.get("name_patterns") or [])
            if name_matches_advertiser(fallback, advertiser_name, require_assembly=True):
                hits.append((did, person.get("side") or "other", "advertiser_name"))
                break
        if not hits or hits[-1][0] != did:
            for ie_pat in ie_patterns.get(did) or []:
                if ie_matches_advertiser(ie_pat, advertiser_name):
                    hits.append((did, "IE", "calaccess_ie_name"))
                    break
    return hits


def load_advertiser_stats(zf: zipfile.ZipFile) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with zf.open(STATS_CSV) as raw:
        reader = csv.DictReader((line.decode("utf-8", errors="replace") for line in raw), delimiter=",")
        for row in reader:
            aid = (row.get("Advertiser_ID") or "").strip()
            if not aid:
                continue
            try:
                total = float(row.get("Spend_USD") or 0)
            except ValueError:
                total = 0.0
            out[aid] = {
                "advertiser_id": aid,
                "advertiser_name": (row.get("Advertiser_Name") or "").strip(),
                "total_spend_usd": total,
                "total_creatives": int(float(row.get("Total_Creatives") or 0)),
                "regions": (row.get("Regions") or "").strip(),
            }
    return out


def load_weekly_spend(zf: zipfile.ZipFile, advertiser_ids: set[str], min_year: int = 2025) -> dict[str, list[dict]]:
    """advertiser_id -> sorted weekly rows (2026 cycle focus)."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    with zf.open(WEEKLY_CSV) as raw:
        reader = csv.DictReader((line.decode("utf-8", errors="replace") for line in raw), delimiter=",")
        for row in reader:
            aid = (row.get("Advertiser_ID") or "").strip()
            if aid not in advertiser_ids:
                continue
            ws = (row.get("Week_Start_Date") or "").strip()
            if not ws:
                continue
            try:
                wk = date.fromisoformat(ws[:10])
            except ValueError:
                continue
            if wk.year < min_year:
                continue
            try:
                spend = float(row.get("Spend_USD") or 0)
            except ValueError:
                spend = 0.0
            buckets[aid].append({"week_start": wk.isoformat(), "spend_usd": spend})
    for aid in buckets:
        buckets[aid].sort(key=lambda x: x["week_start"])
    return buckets


def scan_geo_advertisers(zf: zipfile.ZipFile, known_ids: set[str]) -> dict[str, set[str]]:
    """One pass creative-stats: advertiser_id -> district ids from geo text."""
    geo_map: dict[str, set[str]] = defaultdict(set)
    log("[geo] scanning creative-stats for CA Assembly geo (streaming)…")
    with zf.open(CREATIVE_CSV) as raw:
        header = raw.readline().decode("utf-8", errors="replace").strip().split(",")
        try:
            geo_idx = header.index("Geo_Targeting_Included")
            aid_idx = header.index("Advertiser_ID")
        except ValueError:
            log("[geo] WARNING: expected columns missing in creative-stats")
            return geo_map
        for line in raw:
            try:
                text = line.decode("utf-8", errors="replace")
            except Exception:
                continue
            # Fast filter before csv parse
            if "California" not in text and "california" not in text:
                continue
            m = re.search(r",\s*(AR[0-9]+)\s*,", text)
            if not m:
                continue
            aid = m.group(1)
            if aid in known_ids:
                continue
            geo_start = text.find('"') if text.count('"') > 2 else None
            geo = text
            if "California" not in geo and "california" not in geo:
                continue
            for did, rx in DISTRICT_GEO_RE.items():
                if rx.search(geo):
                    geo_map[aid].add(did)
    log(f"[geo] {len(geo_map)} advertisers with explicit Assembly-district geo")
    return geo_map


def aggregate_district_weekly(advertisers: list[dict]) -> list[dict]:
    """Sum spend_usd by week_start across advertisers."""
    by_week: dict[str, float] = defaultdict(float)
    for adv in advertisers:
        for w in adv.get("weekly") or []:
            by_week[w["week_start"]] += float(w.get("spend_usd") or 0)
    return [{"week_start": k, "spend_usd": round(v, 2)} for k, v in sorted(by_week.items())]


def build_bundle(
    zip_path: Path,
    beach: dict,
    money: dict | None,
    *,
    max_weeks_chart: int = 16,
) -> dict[str, Any]:
    people_by_dist = district_people(beach)
    ie_patterns = ie_name_patterns(money)

    with zipfile.ZipFile(zip_path, "r") as zf:
        updated_pt = read_updated_time(zf)
        stats = load_advertiser_stats(zf)

        # First pass: name-based assignment per advertiser
        adv_assignments: dict[str, list[tuple[str, str, str]]] = {}
        for aid, meta in stats.items():
            if not norm_name(meta["advertiser_name"]):
                continue
            regions = (meta.get("regions") or "").upper()
            if regions and regions != "US":
                continue
            hits = assign_district_by_name(meta["advertiser_name"], people_by_dist, ie_patterns)
            an = norm_name(meta["advertiser_name"])
            if an:
                for did, extras in EXTRA_NAME_MATCHES.items():
                    for label, side in extras:
                        ln = norm_name(label)
                        if not ln:
                            continue
                        if ln in an or (len(an) >= 12 and an in ln):
                            hits.append((did, side, "curated_ie_name"))
            if hits:
                adv_assignments[aid] = hits

        name_matched_ids = set(adv_assignments.keys())
        geo_map = scan_geo_advertisers(zf, name_matched_ids)
        for aid, dists in geo_map.items():
            if aid not in adv_assignments:
                adv_assignments[aid] = []
            for did in dists:
                adv_assignments[aid].append((did, "IE", "geo_targeting"))

        all_ids = set(adv_assignments.keys())
        weekly_by_adv = load_weekly_spend(zf, all_ids)

    districts_out: dict[str, Any] = {}
    for did in BEACHHEAD_IDS:
        advertisers: list[dict] = []
        for aid, hits in adv_assignments.items():
            dist_hits = [h for h in hits if h[0] == did]
            if not dist_hits:
                continue
            meta = stats.get(aid) or {}
            side = dist_hits[0][1]
            reasons = sorted({h[2] for h in dist_hits})
            weekly = weekly_by_adv.get(aid) or []
            if max_weeks_chart and len(weekly) > max_weeks_chart:
                weekly = weekly[-max_weeks_chart:]
            first_seen = weekly[0]["week_start"] if weekly else None
            last_seen = weekly[-1]["week_start"] if weekly else None
            advertisers.append(
                {
                    "advertiser_id": aid,
                    "advertiser_name": meta.get("advertiser_name") or aid,
                    "side": side,
                    "match_reasons": reasons,
                    "total_spend_usd": meta.get("total_spend_usd"),
                    "total_creatives": meta.get("total_creatives"),
                    "weekly": weekly,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "transparency_url": TRANSPARENCY_BASE.format(advertiser_id=aid),
                    "spend_note": "Weekly Spend_USD from google-political-ads-advertiser-weekly-spend.csv (Google-reported totals per week).",
                }
            )

        advertisers.sort(key=lambda a: float(a.get("total_spend_usd") or 0), reverse=True)
        weekly_total = aggregate_district_weekly(advertisers)
        by_side: dict[str, Any] = {}
        for side in ("R", "D", "IE", "other"):
            rows = [a for a in advertisers if a.get("side") == side]
            if not rows:
                continue
            by_side[side] = {
                "advertisers": rows,
                "weekly_total": aggregate_district_weekly(rows),
            }

        districts_out[did] = {
            "id": did,
            "code": did.upper().replace("AD-", "AD-"),
            "has_matched_ads": bool(advertisers),
            "advertisers": advertisers,
            "top_advertisers": advertisers[:8],
            "weekly_total": weekly_total[-max_weeks_chart:] if weekly_total else [],
            "by_side": by_side,
            "matched_advertiser_count": len(advertisers),
            "note": (
                "Google ads only — Meta (Facebook/Instagram) not included; "
                "Meta Ad Library report can be added manually."
            ),
        }

    return {
        "schema_version": 1,
        "product": "MajorityIQ",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of_pt": updated_pt,
        "source": {
            "publisher": "Google",
            "dataset": "Political Ads Transparency bundle",
            "url": BUNDLE_URL,
            "bundle_path": str(zip_path),
            "files_used": [WEEKLY_CSV, STATS_CSV, UPDATED_CSV, CREATIVE_CSV],
            "attribution": "Public Google Political Ads Transparency data. Not a Google endorsement of MajorityIQ.",
        },
        "matching": {
            "methods": [
                "Candidate/committee name patterns from data/calaccess/beachheads.json",
                "CAL-ACCESS IE committee names from money-by-district.json (normalized substring)",
                "Geo_Targeting_Included in creative-stats when explicit CA Assembly district text appears",
            ],
            "limitations": "ZIP-level geo without district numbers is not mapped. Meta not included.",
        },
        "districts": districts_out,
    }


def write_latest(payload: dict, as_of: str | None) -> Path:
    LATEST.mkdir(parents=True, exist_ok=True)
    latest = LATEST / "ads-by-district.json"
    latest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if as_of:
        tag = re.sub(r"[^0-9-]", "-", as_of.split()[0])[:10]
        dated = LATEST / f"ads-by-district-{tag}.json"
        dated.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log(f"[ok] wrote {latest}")
    return latest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build MajorityIQ Google ads JSON")
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--force-download", action="store_true")
    p.add_argument("--zip", type=str, default="", help="Path to existing bundle ZIP")
    args = p.parse_args(argv)

    zip_path = Path(args.zip) if args.zip else None
    if not zip_path:
        if args.skip_download:
            zip_path = OFFLINE / BUNDLE_NAME
            if not zip_path.exists():
                log("ERROR: no bundle in offline/; run without --skip-download")
                return 2
        else:
            zip_path = download_bundle(force=args.force_download)

    beach = load_json(BEACHHEADS)
    money = load_json(MONEY) if MONEY.exists() else None
    payload = build_bundle(zip_path, beach, money)
    write_latest(payload, payload.get("as_of_pt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
