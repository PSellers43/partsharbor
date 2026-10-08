#!/usr/bin/env python3
"""
MajorityIQ CAL-ACCESS daily ingest
====================================
Downloads the official CA Secretary of State raw ZIP, extracts needed TSVs,
maps committees to beachhead Assembly districts, and emits JSON for the
prototype Money panel.

Source (official only):
  https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip
  Documented at:
  https://www.sos.ca.gov/campaign-lobbying/helpful-resources/raw-data-campaign-finance-and-lobbying-activity

Public SOS data. Not an FPPC endorsement. Never invent figures.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.request import Request, urlretrieve

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # data/calaccess/
PROTO = ROOT.parent.parent  # assemblyedge-prototype/
TI_SCRIPTS = ROOT.parent / "threat-index" / "scripts"
if str(TI_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TI_SCRIPTS))
from ti_ie_direction import ie_effect  # noqa: E402
BEACHHEADS_PATH = ROOT / "beachheads.json"
RAW_DIR = ROOT / "raw"
EXTRACT_ROOT = ROOT / "extract"
LATEST_DIR = ROOT / "latest"

OFFICIAL_ZIP_URL = "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"
OFFICIAL_DOCS_URL = "https://campaignfinance.cdn.sos.ca.gov/calaccess-documentation.zip"
OFFICIAL_PAGE = (
    "https://www.sos.ca.gov/campaign-lobbying/helpful-resources/"
    "raw-data-campaign-finance-and-lobbying-activity"
)

# Files we extract from the ZIP (skip multi-GB RCPT_CD / EXPN_CD — use SMRY + late filings)
NEEDED_TSVS = [
    "CalAccess/DATA/CVR_CAMPAIGN_DISCLOSURE_CD.TSV",
    "CalAccess/DATA/FILERNAME_CD.TSV",
    "CalAccess/DATA/SMRY_CD.TSV",
    "CalAccess/DATA/S496_CD.TSV",
    "CalAccess/DATA/S497_CD.TSV",
]

# Form 460 summary line items (FPPC Form 460):
#   5  = TOTAL CONTRIBUTIONS RECEIVED (period col A / YTD col B)
#   11 = TOTAL EXPENDITURES MADE
F460_RECEIPTS_LINE = "5"
F460_SPEND_LINE = "11"

PT = timezone(timedelta(hours=-7))  # America/Los_Angeles approx (PST/PDT label handled separately)

# 2026 general election — FPPC 90-day late reporting period (Form 497 / 496).
# Manual 2 Ch. 11: $1,000+ contributions made/received during the 90 days before the
# election, including election day (https://www.fppc.ca.gov/).
GENERAL_ELECTION_DATE = datetime(2026, 11, 3)
LATE_REPORTING_PERIOD_DAYS = 90
# Calendar start = election minus 90 days (2026-08-05 through 2026-11-03 inclusive).
LATE_MONEY_WINDOW_START = GENERAL_ELECTION_DATE - timedelta(days=LATE_REPORTING_PERIOD_DAYS)


def contrib_in_late_period(cdate: Optional[datetime]) -> bool:
    if not cdate:
        return False
    d = cdate.date()
    return LATE_MONEY_WINDOW_START.date() <= d <= GENERAL_ELECTION_DATE.date()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def today_pt() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d")


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.split(".")[0]
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def norm_dist(d: Optional[str]) -> str:
    d = (d or "").strip()
    if not d:
        return ""
    return d.lstrip("0") or "0"


def norm_name(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def money(n: float) -> float:
    return round(float(n or 0), 2)


def pattern_hit(text: str, patterns: Iterable[str]) -> bool:
    t = norm_name(text)
    for p in patterns:
        if norm_name(p) in t:
            return True
    return False


def open_tsv(path: Path):
    # CAL-ACCESS TSVs are historically latin-1 / cp1252
    return open(path, newline="", encoding="latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Download / extract
# ---------------------------------------------------------------------------

def download_zip(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = today_pt()
    dest = RAW_DIR / f"dbwebexport-{date_tag}.zip"
    if dest.exists() and dest.stat().st_size > 1_000_000 and not force:
        log(f"[skip] ZIP already present: {dest} ({dest.stat().st_size:,} bytes)")
        return dest
    log(f"[download] {OFFICIAL_ZIP_URL}")
    log(f"           → {dest}")
    tmp = dest.with_suffix(".partial")
    try:
        def _reporthook(block, block_size, total):
            if not hasattr(_reporthook, "_last"):
                _reporthook._last = 0
            done = block * block_size
            if total > 0 and done - _reporthook._last > 50_000_000:
                pct = 100.0 * done / total
                log(f"  … {pct:.0f}% ({done/1e6:.0f}/{total/1e6:.0f} MB)")
                _reporthook._last = done

        urlretrieve(OFFICIAL_ZIP_URL, tmp, reporthook=_reporthook)
        tmp.replace(dest)
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"Download failed: {e}") from e
    log(f"[ok] downloaded {dest.stat().st_size:,} bytes")
    return dest


def extract_needed(zip_path: Path, date_tag: Optional[str] = None) -> Path:
    date_tag = date_tag or today_pt()
    out = EXTRACT_ROOT / date_tag
    out.mkdir(parents=True, exist_ok=True)
    missing = [name for name in NEEDED_TSVS if not (out / Path(name).name).exists()]
    if not missing:
        log(f"[skip] extract already has needed TSVs in {out}")
        return out
    log(f"[extract] {zip_path.name} → {out}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        for member in NEEDED_TSVS:
            if member not in names:
                # try case variants
                alt = next((n for n in names if n.upper().endswith(Path(member).name.upper())), None)
                if not alt:
                    log(f"  WARNING: {member} not in ZIP")
                    continue
                member = alt
            log(f"  extracting {member} …")
            zf.extract(member, out)
            src = out / member
            dest = out / Path(member).name
            if src != dest:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
    # cleanup nested dirs
    nested = out / "CalAccess"
    if nested.exists():
        shutil.rmtree(nested, ignore_errors=True)
    for name in NEEDED_TSVS:
        p = out / Path(name).name
        if not p.exists():
            raise FileNotFoundError(f"Expected extract missing: {p}")
    return out


# ---------------------------------------------------------------------------
# Matching + rollups
# ---------------------------------------------------------------------------

def load_beachheads() -> dict:
    with open(BEACHHEADS_PATH, encoding="utf-8") as f:
        return json.load(f)


def collect_cvr_rows(extract_dir: Path, dist_nos: Set[str], min_year: int) -> List[dict]:
    """Load CVR campaign disclosure rows for ASM + beachhead districts since min_year."""
    path = extract_dir / "CVR_CAMPAIGN_DISCLOSURE_CD.TSV"
    rows: List[dict] = []
    with open_tsv(path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if (row.get("OFFICE_CD") or "").strip().upper() != "ASM":
                continue
            dist = norm_dist(row.get("DIST_NO"))
            if dist not in dist_nos:
                continue
            rpt = parse_dt(row.get("RPT_DATE"))
            thru = parse_dt(row.get("THRU_DATE"))
            elect = parse_dt(row.get("ELECT_DATE"))
            years = [d.year for d in (rpt, thru, elect) if d]
            if not years or max(years) < min_year:
                continue
            cand = f"{(row.get('CAND_NAMF') or '').strip()} {(row.get('CAND_NAML') or '').strip()}".strip()
            filer = f"{(row.get('FILER_NAMF') or '').strip()} {(row.get('FILER_NAML') or '').strip()}".strip()
            rows.append({
                "filing_id": (row.get("FILING_ID") or "").strip(),
                "amend_id": int((row.get("AMEND_ID") or "0").strip() or 0),
                "filer_id": (row.get("FILER_ID") or "").strip(),
                "form": (row.get("FORM_TYPE") or "").strip().upper(),
                "entity": (row.get("ENTITY_CD") or "").strip().upper(),
                "filer": filer,
                "cand": cand or filer,
                "dist": dist,
                "rpt": rpt,
                "thru": thru,
                "from_dt": parse_dt(row.get("FROM_DATE")),
                "elect": elect,
                "sup_opp": (row.get("SUP_OPP_CD") or "").strip().upper(),
                "cmtte_type": (row.get("CMTTE_TYPE") or "").strip().upper(),
            })
    return rows


def score_committee_for_person(filer: str, cand: str, person: dict, cycle_year: int) -> Tuple[int, str]:
    """Return (score, reason). Higher is better. Prefer cycle-year committees."""
    blob = f"{filer} {cand}"
    score = 0
    reasons = []
    # committee pattern
    for p in person.get("committee_patterns") or []:
        if pattern_hit(filer, [p]):
            score += 50
            reasons.append(f"committee~{p}")
            break
    # name pattern on candidate or filer
    for p in person.get("name_patterns") or []:
        if pattern_hit(cand, [p]) or pattern_hit(filer, [p]):
            score += 30
            reasons.append(f"name~{p}")
            break
    # cycle year bonus
    if str(cycle_year) in filer:
        score += 40
        reasons.append(f"year={cycle_year}")
    elif str(cycle_year - 2) in filer:
        score += 5
        reasons.append("prior-cycle-committee")
    # exclude ballot measure / officeholder-only if better options exist
    up = filer.upper()
    if "BALLOT MEASURE" in up or "RESTORE CALIFORNIA" in up:
        score -= 25
        reasons.append("ballot-measure-penalty")
    if "OFFICEHOLDER" in up and str(cycle_year) not in filer:
        score -= 15
        reasons.append("officeholder-penalty")
    return score, ",".join(reasons) or "weak"


def ballot_role_label(kind: str, person: dict, district: dict) -> str:
    """Human-readable candidate role for Money panel (SOS-certified general roster)."""
    party = (person.get("party") or "").strip().upper()
    if kind == "incumbent":
        return "Incumbent"
    if district.get("open_seat"):
        return f"Open seat – {party}" if party in ("R", "D") else "Open seat"
    if (person.get("ballot_status") or "general") == "primary_only":
        return "Primary (did not advance)"
    return "Opponent"


def district_ballot_people(district: dict) -> List[Tuple[str, dict]]:
    """Configured people on the Nov general ballot (incumbent + GE opponents or open-seat pair)."""
    out: List[Tuple[str, dict]] = []
    if district.get("open_seat"):
        for person in district.get("general_candidates") or []:
            out.append(("open_seat", person))
        return out
    inc = district.get("incumbent")
    if inc:
        out.append(("incumbent", inc))
    for opp in district.get("known_opponents") or []:
        if (opp.get("ballot_status") or "general") == "primary_only":
            continue
        out.append(("opponent", opp))
    return out


def claim_primary_non_advancing(
    district: dict,
    cycle_year: int,
    claimed_filer_ids: Set[str],
    cand_filings: List[dict],
) -> None:
    """Match primary-only committees so they are not auto-discovered as general opponents."""
    dist = district["dist_no"]
    for person in district.get("primary_non_advancing") or []:
        by_filer: Dict[str, List[dict]] = defaultdict(list)
        for r in cand_filings:
            if r["dist"] != dist:
                continue
            by_filer[r["filer_id"]].append(r)
        for filer_id, rows in by_filer.items():
            if filer_id in claimed_filer_ids:
                continue
            rows_sorted = sorted(rows, key=lambda x: x["rpt"] or datetime.min, reverse=True)
            filer_name = rows_sorted[0]["filer"]
            cand_name = rows_sorted[0]["cand"]
            sc, _reason = score_committee_for_person(filer_name, cand_name, person, cycle_year)
            if sc >= 40:
                claimed_filer_ids.add(filer_id)


def pick_candidate_committees(
    cvr_rows: List[dict], district: dict, cycle_year: int
) -> Dict[str, Any]:
    """
    For a beachhead district, pick best CTL/CAO F460 committee per configured
    general-election roster (incumbent + opponents, or open-seat pair). Also
    discover other 2026 'for Assembly' CTL committees in-district as unmatched/extra
    opponents unless claimed as primary_non_advancing.
    """
    dist = district["dist_no"]
    people = [(kind, person) for kind, person in district_ballot_people(district)]

    # candidate committees: F460 with entity CTL/CAO (controlled/candidate)
    cand_filings = [
        r for r in cvr_rows
        if r["dist"] == dist
        and r["form"] == "F460"
        and r["entity"] in ("CTL", "CAO", "RCP")
    ]

    results = []
    claimed_filer_ids: Set[str] = set()

    for role, person in people:
        best: Dict[str, Any] = {}
        # score unique filer_ids
        by_filer: Dict[str, List[dict]] = defaultdict(list)
        for r in cand_filings:
            by_filer[r["filer_id"]].append(r)
        scored = []
        for filer_id, rows in by_filer.items():
            if filer_id in claimed_filer_ids:
                continue
            # representative filer name = most recent
            rows_sorted = sorted(rows, key=lambda x: x["rpt"] or datetime.min, reverse=True)
            filer_name = rows_sorted[0]["filer"]
            cand_name = rows_sorted[0]["cand"]
            sc, reason = score_committee_for_person(filer_name, cand_name, person, cycle_year)
            if sc < 40:
                continue
            scored.append((sc, reason, filer_id, filer_name, cand_name, rows_sorted))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            results.append({
                "role": ballot_role_label(role, person, district),
                "name": person["name"],
                "party": person.get("party"),
                "match_quality": "unmatched",
                "match_score": 0,
                "match_reason": "no committee scored >= 40",
                "filer_id": None,
                "committee_name": None,
                "filing_ids": [],
            })
            continue
        sc, reason, filer_id, filer_name, cand_name, rows_sorted = scored[0]
        claimed_filer_ids.add(filer_id)
        # latest amend per filing_id
        latest_amend: Dict[str, int] = {}
        for r in rows_sorted:
            fid = r["filing_id"]
            latest_amend[fid] = max(latest_amend.get(fid, -1), r["amend_id"])
        quality = "strong" if sc >= 90 else ("moderate" if sc >= 60 else "weak")
        results.append({
            "role": ballot_role_label(role, person, district),
            "name": person["name"],
            "display_name": cand_name or person["name"],
            "party": person.get("party"),
            "match_quality": quality,
            "match_score": sc,
            "match_reason": reason,
            "filer_id": filer_id,
            "committee_name": filer_name,
            "filing_ids": sorted(latest_amend.keys()),
            "filing_amends": {k: v for k, v in latest_amend.items()},
            "latest_rpt": (rows_sorted[0]["rpt"].isoformat() if rows_sorted[0]["rpt"] else None),
            "latest_thru": (rows_sorted[0]["thru"].isoformat() if rows_sorted[0]["thru"] else None),
        })

    claim_primary_non_advancing(district, cycle_year, claimed_filer_ids, cand_filings)

    # General-election roster is beachheads-only (SOS certified). Do not auto-add other CTL committees.

    return {"candidates": results, "claimed_filer_ids": claimed_filer_ids}


def load_smry_for_filings(extract_dir: Path, filing_amends: Dict[str, int]) -> Dict[Tuple[str, int], Dict[str, float]]:
    """Return {(filing_id, amend_id): {line_item: amount_a}} for F460 rows we need."""
    wanted = {(fid, int(aid)) for fid, aid in filing_amends.items()}
    out: Dict[Tuple[str, int], Dict[str, float]] = defaultdict(dict)
    if not wanted:
        return out
    path = extract_dir / "SMRY_CD.TSV"
    with open_tsv(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            fid = (row.get("FILING_ID") or "").strip()
            try:
                aid = int((row.get("AMEND_ID") or "0").strip() or 0)
            except ValueError:
                continue
            if (fid, aid) not in wanted:
                continue
            if (row.get("FORM_TYPE") or "").strip() != "F460":
                continue
            li = (row.get("LINE_ITEM") or "").strip()
            if li not in (F460_RECEIPTS_LINE, F460_SPEND_LINE, "16"):
                continue
            try:
                amt = float((row.get("AMOUNT_A") or "0").strip() or 0)
            except ValueError:
                amt = 0.0
            out[(fid, aid)][li] = amt
    return out


def rollup_candidate_money(cand: dict, smry: Dict[Tuple[str, int], Dict[str, float]]) -> dict:
    if not cand.get("filer_id"):
        return {
            **cand,
            "receipts": None,
            "spend": None,
            "cash_on_hand_latest": None,
            "provenance": {"status": "unmatched", "source": None},
        }
    amends = cand.get("filing_amends") or {}
    receipts = 0.0
    spend = 0.0
    coh = None
    used = []
    # pick latest thru filing for cash-on-hand
    latest_fid = None
    for fid, aid in amends.items():
        lines = smry.get((fid, int(aid)), {})
        r = lines.get(F460_RECEIPTS_LINE, 0.0)
        s = lines.get(F460_SPEND_LINE, 0.0)
        receipts += r
        spend += s
        used.append({
            "filing_id": fid,
            "amend_id": int(aid),
            "receipts_period": money(r),
            "spend_period": money(s),
            "form": "F460",
            "lines": {"5": "total contributions received (period)", "11": "total expenditures made (period)"},
        })
        latest_fid = fid  # overwritten; refine below
    # cash on hand from filing with max filing_id as proxy for recency if thru unknown
    if amends:
        # prefer highest filing_id
        best = max(amends.items(), key=lambda kv: int(kv[0]))
        lines = smry.get((best[0], int(best[1])), {})
        coh = lines.get("16")
    return {
        **cand,
        "receipts": money(receipts),
        "spend": money(spend),
        "cash_on_hand_latest": money(coh) if coh is not None else None,
        "provenance": {
            "status": "live",
            "source": "SMRY_CD Form 460 lines 5 & 11 (sum of period AMOUNT_A across cycle filings, latest amend)",
            "filer_id": cand["filer_id"],
            "committee_name": cand.get("committee_name"),
            "filings": used,
        },
    }


def collect_ie_for_district(
    cvr_rows: List[dict],
    extract_dir: Path,
    dist: str,
    candidate_names: List[str],
    cycle_year: int,
) -> List[dict]:
    """
    Independent expenditures (Form 496) targeting candidates in this district.
    Join CVR (candidate + support/oppose) to S496 amounts.
    """
    # F496 cover rows for this dist
    covers = [
        r for r in cvr_rows
        if r["dist"] == dist and r["form"] in ("F496", "F465")
    ]
    # Keep cycle-relevant (rpt year >= cycle_year-1)
    covers = [
        r for r in covers
        if (r["rpt"] and r["rpt"].year >= cycle_year - 1)
        or (r["elect"] and r["elect"].year >= cycle_year - 1)
    ]
    # latest amend per filing
    best: Dict[str, dict] = {}
    for r in covers:
        prev = best.get(r["filing_id"])
        if not prev or r["amend_id"] > prev["amend_id"]:
            best[r["filing_id"]] = r

    filing_amends = {fid: r["amend_id"] for fid, r in best.items()}
    # Load S496 amounts
    amounts: Dict[Tuple[str, int], List[dict]] = defaultdict(list)
    path = extract_dir / "S496_CD.TSV"
    with open_tsv(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            fid = (row.get("FILING_ID") or "").strip()
            if fid not in filing_amends:
                continue
            try:
                aid = int((row.get("AMEND_ID") or "0").strip() or 0)
            except ValueError:
                continue
            if aid != filing_amends[fid]:
                continue
            try:
                amt = float((row.get("AMOUNT") or "0").strip() or 0)
            except ValueError:
                amt = 0.0
            amounts[(fid, aid)].append({
                "amount": amt,
                "exp_date": parse_dt(row.get("EXP_DATE")),
                "desc": (row.get("EXPN_DSCR") or "").strip(),
                "tran_id": (row.get("TRAN_ID") or "").strip(),
            })

    # Aggregate by (IE filer, side, target cand)
    agg: Dict[Tuple[str, str, str], dict] = {}
    for fid, cover in best.items():
        aid = cover["amend_id"]
        items = amounts.get((fid, aid), [])
        total = sum(i["amount"] for i in items)
        if total == 0 and not items:
            continue
        side = "support" if cover["sup_opp"] == "S" else ("oppose" if cover["sup_opp"] == "O" else "unknown")
        target = cover["cand"] or "unknown"
        key = (cover["filer_id"], side, norm_name(target))
        slot = agg.setdefault(key, {
            "filer_id": cover["filer_id"],
            "name": cover["filer"],
            "side": side,
            "target": target,
            "spend": 0.0,
            "receipts": 0.0,  # IE schedules don't give committee receipts here
            "exp_dates": [],
            "filing_ids": [],
            "line_count": 0,
        })
        slot["spend"] += total
        slot["filing_ids"].append(fid)
        slot["line_count"] += len(items)
        for i in items:
            if i["exp_date"]:
                slot["exp_dates"].append(i["exp_date"])

    # Optional: filter to our candidate name patterns if we have them
    name_norms = [norm_name(n) for n in candidate_names if n]
    out = []
    for slot in agg.values():
        tgt = norm_name(slot["target"])
        if name_norms and not any(n in tgt or tgt in n for n in name_norms if len(n) > 3):
            # still keep if target empty/unknown? skip weak
            if tgt and tgt != "UNKNOWN":
                # keep IE that name-match any beachhead cand substring
                if not any(n.split()[-1] in tgt for n in name_norms if n):
                    continue
        out.append(slot)
    return out


def wow_and_series(exp_dates: List[datetime], amounts_by_date: Optional[Dict[datetime, float]] = None) -> Tuple[Optional[float], List[float]]:
    """
    Compute WoW % change in spend using last 7 days vs prior 7 days from exp_dates.
    Also build 8 weekly buckets (oldest→newest) counting events or summing amounts.
    """
    if not exp_dates:
        return None, [0, 0, 0, 0, 0, 0, 0, 0]
    now = max(exp_dates)
    # If amounts_by_date not provided, count events as proxy intensity
    week_sums = [0.0] * 8
    for d in exp_dates:
        days_ago = (now.date() - d.date()).days
        week_idx = 7 - min(7, days_ago // 7)  # 0=oldest of 8w window-ish
        # Better: bucket relative to now
        w = days_ago // 7
        if 0 <= w < 8:
            idx = 7 - w
            if amounts_by_date and d.date() in {x.date() if isinstance(x, datetime) else x for x in amounts_by_date}:
                week_sums[idx] += 1
            else:
                week_sums[idx] += 1
    # WoW from last two weeks of the series
    last = week_sums[7]
    prev = week_sums[6]
    if prev == 0 and last == 0:
        delta = 0.0
    elif prev == 0:
        delta = 100.0 if last > 0 else 0.0
    else:
        delta = round(100.0 * (last - prev) / prev, 1)
    return delta, [round(x, 2) for x in week_sums]


def build_ie_entities(ie_slots: List[dict], as_of: datetime) -> List[dict]:
    """Collapse IE slots into top support/oppose entities with WoW + series."""
    # Group by (name, side) — sum targets
    grouped: Dict[Tuple[str, str], dict] = {}
    for s in ie_slots:
        key = (s["name"], s["side"])
        g = grouped.setdefault(key, {
            "name": s["name"],
            "side": s["side"],
            "filer_id": s["filer_id"],
            "spend": 0.0,
            "receipts": 0.0,
            "targets": set(),
            "exp_dates": [],
            "filing_ids": [],
        })
        g["spend"] += s["spend"]
        g["targets"].add(s["target"])
        g["exp_dates"].extend(s["exp_dates"])
        g["filing_ids"].extend(s["filing_ids"])

    entities = []
    for g in grouped.values():
        delta, series = wow_and_series(g["exp_dates"])
        # scale series to reflect spend distribution roughly by event share
        total_events = sum(series) or 1
        series_scaled = [round(g["spend"] * (v / total_events), 2) for v in series]
        entities.append({
            "name": g["name"][:120],
            "side": g["side"],
            "role": f"IE {g['side']}",
            "receipts": money(g["receipts"]),
            "spend": money(g["spend"]),
            "deltaSpend": delta if delta is not None else 0,
            "deltaReceipts": 0,
            "series": series_scaled,
            "targets": sorted(t for t in g["targets"] if t),
            "match_quality": "live",
            "provenance": {
                "source": "S496_CD amounts joined to CVR_CAMPAIGN_DISCLOSURE F496/F465 covers",
                "filer_id": g["filer_id"],
                "filing_ids": sorted(set(g["filing_ids"]))[:20],
                "filing_id_count": len(set(g["filing_ids"])),
            },
        })
    # Sort: oppose first by spend, then support
    entities.sort(key=lambda e: (0 if e["side"] == "oppose" else 1, -e["spend"]))
    return entities


def person_display_name(namf: str, naml: str, namt: str = "", nams: str = "") -> str:
    parts = [(namt or "").strip(), (namf or "").strip(), (naml or "").strip(), (nams or "").strip()]
    return " ".join(p for p in parts if p).strip() or "Unknown"


def load_f497_cover_index(extract_dir: Path, filer_ids: Set[str]) -> Dict[str, dict]:
    """Latest-amend F497 cover row per FILING_ID for the given filer IDs."""
    if not filer_ids:
        return {}
    path = extract_dir / "CVR_CAMPAIGN_DISCLOSURE_CD.TSV"
    best: Dict[str, dict] = {}
    with open_tsv(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if (row.get("FORM_TYPE") or "").strip().upper() != "F497":
                continue
            fid = (row.get("FILER_ID") or "").strip()
            if fid not in filer_ids:
                continue
            filing_id = (row.get("FILING_ID") or "").strip()
            if not filing_id:
                continue
            try:
                aid = int((row.get("AMEND_ID") or "0").strip() or 0)
            except ValueError:
                aid = 0
            prev = best.get(filing_id)
            if not prev or aid > int(prev.get("_amend_id") or 0):
                filer = person_display_name(
                    row.get("FILER_NAMF") or "",
                    row.get("FILER_NAML") or "",
                )
                best[filing_id] = {
                    "filing_id": filing_id,
                    "amend_id": aid,
                    "filer_id": fid,
                    "filer_name": filer or fid,
                    "rpt_date": parse_dt(row.get("RPT_DATE")),
                    "_amend_id": aid,
                }
    return best


def s497_entity_label(row: dict) -> str:
    return person_display_name(
        row.get("ENTY_NAMF") or "",
        row.get("ENTY_NAML") or "",
        row.get("ENTY_NAMT") or "",
        row.get("ENTY_NAMS") or "",
    )


def s497_cand_label(row: dict) -> str:
    return person_display_name(
        row.get("CAND_NAMF") or "",
        row.get("CAND_NAML") or "",
        row.get("CAND_NAMT") or "",
        row.get("CAND_NAMS") or "",
    )


def election_date_ok(elec_dt: Optional[datetime], cycle_year: int) -> bool:
    """Keep rows tied to the cycle general or unset election date."""
    if not elec_dt:
        return True
    if elec_dt.date() == GENERAL_ELECTION_DATE.date():
        return True
    if elec_dt.year == cycle_year and elec_dt >= datetime(cycle_year, 6, 1):
        return True
    return False


def collect_late_s497_items(
    extract_dir: Path,
    district: dict,
    filer_to_district: Dict[str, str],
    beach_dist_nos: Set[str],
    cycle_year: int,
) -> Tuple[List[dict], int]:
    """
    Form 497 schedule lines for a district (latest amend per filing only).
    Returns (items in tracking window, count of linked F497 filings for district filers).
    """
    dist_no = district["dist_no"]
    dist_id = district["id"]
    filer_ids = {fid for fid, did in filer_to_district.items() if did == dist_id}
    covers = load_f497_cover_index(extract_dir, filer_ids)
    filing_amends = {fid: c["amend_id"] for fid, c in covers.items()}
    if not filing_amends:
        return [], 0

    items: List[dict] = []
    seen_keys: Set[Tuple[str, int, str]] = set()
    path = extract_dir / "S497_CD.TSV"
    with open_tsv(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            filing_id = (row.get("FILING_ID") or "").strip()
            if filing_id not in filing_amends:
                continue
            try:
                aid = int((row.get("AMEND_ID") or "0").strip() or 0)
            except ValueError:
                continue
            if aid != filing_amends[filing_id]:
                continue
            tran_id = (row.get("TRAN_ID") or "").strip() or str(row.get("LINE_ITEM") or "")
            dedupe_key = (filing_id, aid, tran_id)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            cover = covers[filing_id]
            office = (row.get("OFFICE_CD") or "").strip().upper()
            line_dist = norm_dist(row.get("DIST_NO"))
            elec_dt = parse_dt(row.get("ELEC_DATE"))
            cdate = parse_dt(row.get("CTRIB_DATE"))

            assigned = cover["filer_id"] in filer_ids
            if not assigned and office == "ASM" and line_dist == dist_no and line_dist in beach_dist_nos:
                if election_date_ok(elec_dt, cycle_year):
                    assigned = True
            if not assigned:
                continue

            form = (row.get("FORM_TYPE") or "").strip().upper()
            direction = "received" if form == "F497P1" else ("made" if form == "F497P2" else "unknown")
            try:
                amt = float((row.get("AMOUNT") or "0").strip() or 0)
            except ValueError:
                amt = 0.0
            sup_opp = (row.get("SUP_OPP_CD") or "").strip().upper()
            side = "support" if sup_opp == "S" else ("oppose" if sup_opp == "O" else None)
            entity = s497_entity_label(row)
            cand = s497_cand_label(row)
            employer = (row.get("CTRIB_EMP") or "").strip() or None
            occupation = (row.get("CTRIB_OCC") or "").strip() or None

            in_period = contrib_in_late_period(cdate)

            items.append({
                "filing_id": filing_id,
                "amend_id": aid,
                "tran_id": tran_id,
                "form": form,
                "direction": direction,
                "amount": money(amt),
                "contrib_date": cdate.date().isoformat() if cdate else None,
                "report_date": cover["rpt_date"].date().isoformat() if cover.get("rpt_date") else None,
                "committee_filer_id": cover["filer_id"],
                "committee_name": cover["filer_name"],
                "entity": entity[:160],
                "entity_type": (row.get("ENTITY_CD") or "").strip().upper() or None,
                "candidate": cand[:120] if cand else None,
                "side": side,
                "employer": employer[:120] if employer else None,
                "occupation": occupation[:60] if occupation else None,
                "in_period": in_period,
            })

    return items, len(covers)


def collect_late_ie_items(
    cvr_rows: List[dict],
    extract_dir: Path,
    dist: str,
    candidate_names: List[str],
    cycle_year: int,
) -> List[dict]:
    """Independent expenditure lines (S496) with expenditure dates in the late-money window."""
    covers = [
        r for r in cvr_rows
        if r["dist"] == dist and r["form"] in ("F496", "F465")
    ]
    covers = [
        r for r in covers
        if (r["rpt"] and r["rpt"].year >= cycle_year - 1)
        or (r["elect"] and r["elect"].year >= cycle_year - 1)
    ]
    best: Dict[str, dict] = {}
    for r in covers:
        prev = best.get(r["filing_id"])
        if not prev or r["amend_id"] > prev["amend_id"]:
            best[r["filing_id"]] = r
    filing_amends = {fid: r["amend_id"] for fid, r in best.items()}
    if not filing_amends:
        return []

    name_norms = [norm_name(n) for n in candidate_names if n]
    out: List[dict] = []
    path = extract_dir / "S496_CD.TSV"
    with open_tsv(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            fid = (row.get("FILING_ID") or "").strip()
            if fid not in filing_amends:
                continue
            try:
                aid = int((row.get("AMEND_ID") or "0").strip() or 0)
            except ValueError:
                continue
            if aid != filing_amends[fid]:
                continue
            exp_dt = parse_dt(row.get("EXP_DATE"))
            if not exp_dt:
                continue
            if not contrib_in_late_period(exp_dt):
                continue
            try:
                amt = float((row.get("AMOUNT") or "0").strip() or 0)
            except ValueError:
                amt = 0.0
            cover = best[fid]
            side = "support" if cover["sup_opp"] == "S" else ("oppose" if cover["sup_opp"] == "O" else "unknown")
            target = cover["cand"] or "unknown"
            tgt = norm_name(target)
            if name_norms and tgt and tgt != "UNKNOWN":
                if not any(n in tgt or tgt in n for n in name_norms if len(n) > 3):
                    if not any(n.split()[-1] in tgt for n in name_norms if n):
                        continue
            out.append({
                "filing_id": fid,
                "amend_id": aid,
                "tran_id": (row.get("TRAN_ID") or "").strip() or None,
                "amount": money(amt),
                "exp_date": exp_dt.date().isoformat(),
                "filer_id": cover["filer_id"],
                "name": cover["filer"][:120],
                "side": side,
                "target": target[:120],
                "description": ((row.get("EXPN_DSCR") or "").strip() or None),
            })
    return out


def filer_to_candidate_meta(district_money: dict) -> Dict[str, dict]:
    """Map committee filer_id → {name, party, role} from matched money rollups."""
    out: Dict[str, dict] = {}
    for c in district_money.get("candidates") or []:
        fid = c.get("filer_id")
        if not fid:
            continue
        out[str(fid)] = {
            "name": c.get("name") or "",
            "party": c.get("party"),
            "role": c.get("role"),
        }
    return out


def enrich_late_s497_items(items: List[dict], filer_meta: Dict[str, dict]) -> None:
    """Fill missing S497 candidate labels from the matched committee roster (avoids UI '→ Unknown')."""
    for item in items:
        fid = str(item.get("committee_filer_id") or "")
        meta = filer_meta.get(fid) or {}
        cand = (item.get("candidate") or "").strip()
        if not cand or cand.upper() == "UNKNOWN":
            if meta.get("name"):
                item["candidate"] = meta["name"]
        if not item.get("side") and meta.get("party") in ("R", "D"):
            item["beneficiary_party"] = meta["party"]


def build_late_money_district_payload(
    district: dict,
    district_money: dict,
    cvr_rows: List[dict],
    extract_dir: Path,
    filer_to_district: Dict[str, str],
    beach_dist_nos: Set[str],
    cycle_year: int,
) -> dict:
    cand_names = [c.get("name") or "" for c in district_money.get("candidates") or []]
    for _kind, person in district_ballot_people(district):
        cand_names.append(person.get("name") or "")

    s497_items, linked_f497 = collect_late_s497_items(
        extract_dir, district, filer_to_district, beach_dist_nos, cycle_year
    )
    enrich_late_s497_items(s497_items, filer_to_candidate_meta(district_money))
    period_items = [i for i in s497_items if i.get("in_period")]
    ie_items = collect_late_ie_items(
        cvr_rows, extract_dir, district["dist_no"], cand_names, cycle_year
    )

    try:
        as_of_date = datetime.strptime(extract_dir.name, "%Y-%m-%d").date()
    except ValueError:
        as_of_date = datetime.now(PT).date()
    win_start = LATE_MONEY_WINDOW_START.date()
    win_end = GENERAL_ELECTION_DATE.date()

    def sum_amount(rows: List[dict], key: str = "amount") -> float:
        return money(sum(float(r.get(key) or 0) for r in rows))

    period_total = sum_amount(period_items)
    received_total = sum_amount([i for i in period_items if i["direction"] == "received"])
    made_total = sum_amount([i for i in period_items if i["direction"] == "made"])
    ie_total = sum_amount(ie_items)
    ie_support = sum_amount([i for i in ie_items if i["side"] == "support"])
    ie_oppose = sum_amount([i for i in ie_items if i["side"] == "oppose"])

    ie_pro_r = ie_anti_r = 0.0
    ie_seven_pro = ie_seven_anti = 0.0
    seven_start = max(win_start, as_of_date - timedelta(days=6))
    for item in ie_items:
        effect = ie_effect(item.get("side") or "", item.get("target") or "", district)
        if effect is None:
            continue
        amt = float(item.get("amount") or 0)
        if effect == "pro_r":
            ie_pro_r += amt
        else:
            ie_anti_r += amt
        exp = item.get("exp_date")
        if exp and seven_start.isoformat() <= exp <= as_of_date.isoformat():
            if effect == "pro_r":
                ie_seven_pro += amt
            else:
                ie_seven_anti += amt

    contrib_dates = sorted({i.get("contrib_date") for i in period_items if i.get("contrib_date")})
    last_filed_day_date = contrib_dates[-1] if contrib_dates else None
    last_24h_total = sum_amount(
        [i for i in period_items if i.get("contrib_date") == as_of_date.isoformat()]
    )
    last_filed_day_total = sum_amount(
        [i for i in period_items if i.get("contrib_date") == last_filed_day_date]
    ) if last_filed_day_date else 0.0
    seven_day_total = sum_amount(
        [
            i for i in period_items
            if i.get("contrib_date")
            and seven_start.isoformat() <= i["contrib_date"] <= as_of_date.isoformat()
        ]
    )
    exp_dates = sorted({i.get("exp_date") for i in ie_items if i.get("exp_date")})
    last_ie_filed_day = exp_dates[-1] if exp_dates else None
    ie_last_24h = sum_amount([i for i in ie_items if i.get("exp_date") == as_of_date.isoformat()])
    ie_last_filed_day = sum_amount(
        [i for i in ie_items if i.get("exp_date") == last_ie_filed_day]
    ) if last_ie_filed_day else 0.0
    ie_seven_day = sum_amount(
        [
            i for i in ie_items
            if i.get("exp_date")
            and seven_start.isoformat() <= i["exp_date"] <= as_of_date.isoformat()
        ]
    )
    # Daily buckets across the full FPPC 90-day period (sparkline + timeline)
    day_cursor = win_start
    daily_buckets: List[dict] = []
    sparkline: List[float] = []
    while day_cursor <= win_end:
        iso = day_cursor.isoformat()
        day_rows = [i for i in period_items if i.get("contrib_date") == iso]
        amt = sum_amount(day_rows)
        daily_buckets.append({"date": iso, "amount": amt, "count": len(day_rows)})
        sparkline.append(amt)
        day_cursor += timedelta(days=1)

    # Top donors: received contributions only, aggregate by contributor entity
    donor_agg: Dict[str, dict] = {}
    for i in period_items:
        if i["direction"] != "received":
            continue
        key = norm_name(i.get("entity") or "")
        if not key:
            continue
        slot = donor_agg.setdefault(key, {
            "name": i.get("entity") or "Unknown",
            "amount": 0.0,
            "count": 0,
            "employer": i.get("employer"),
        })
        slot["amount"] += float(i.get("amount") or 0)
        slot["count"] += 1
    top_donors = sorted(donor_agg.values(), key=lambda x: -x["amount"])[:8]
    for d in top_donors:
        d["amount"] = money(d["amount"])

    recent = sorted(
        period_items,
        key=lambda x: (x.get("contrib_date") or "", x.get("report_date") or ""),
        reverse=True,
    )[:60]

    recent_ie = sorted(ie_items, key=lambda x: x.get("exp_date") or "", reverse=True)[:20]

    return {
        "id": district["id"],
        "code": district["code"],
        "dist_no": district["dist_no"],
        "as_of_date": as_of_date.isoformat(),
        "window": {
            "start": win_start.isoformat(),
            "end": win_end.isoformat(),
            "days": LATE_REPORTING_PERIOD_DAYS,
            "election_date": win_end.isoformat(),
            "authority": "FPPC Manual 2 Ch. 11 (90-day election cycle, includes election day)",
        },
        "linked_f497_filings": linked_f497,
        "totals": {
            "period_contributions": money(period_total),
            "period_contribution_reports": len(period_items),
            "received": money(received_total),
            "made": money(made_total),
            "last_24h": money(last_24h_total),
            "last_filed_day": money(last_filed_day_total),
            "last_filed_day_date": last_filed_day_date,
            "seven_day": money(seven_day_total),
            "ie_period": money(ie_total),
            "ie_last_24h": money(ie_last_24h),
            "ie_last_filed_day": money(ie_last_filed_day),
            "ie_last_filed_day_date": last_ie_filed_day,
            "ie_seven_day": money(ie_seven_day),
            "ie_seven_day_pro_r": money(ie_seven_pro),
            "ie_seven_day_anti_r": money(ie_seven_anti),
            "ie_support": money(ie_support),
            "ie_oppose": money(ie_oppose),
            "ie_pro_r": money(ie_pro_r),
            "ie_anti_r": money(ie_anti_r),
            "ie_reports": len(ie_items),
        },
        "sparkline": sparkline,
        "daily_buckets": daily_buckets,
        "top_donors": top_donors,
        "recent_contributions": recent,
        "recent_ie": recent_ie,
        "empty": len(period_items) == 0 and len(ie_items) == 0,
    }


def build_late_money_bundle(
    beach: dict,
    districts_money: Dict[str, dict],
    cvr_rows: List[dict],
    extract_dir: Path,
    as_of: str,
    zip_as_of: Optional[str],
) -> dict:
    cycle_year = int(beach.get("cycle_year") or 2026)
    beach_dist_nos = {d["dist_no"] for d in beach["districts"]}
    filer_to_district: Dict[str, str] = {}
    for d in beach["districts"]:
        did = d["id"]
        dm = districts_money.get(did) or {}
        for c in dm.get("candidates") or []:
            fid = c.get("filer_id")
            if fid:
                filer_to_district[str(fid)] = did

    districts_out = {}
    summary = []
    for d in beach["districts"]:
        dm = districts_money.get(d["id"]) or {}
        payload = build_late_money_district_payload(
            d, dm, cvr_rows, extract_dir, filer_to_district, beach_dist_nos, cycle_year
        )
        districts_out[d["id"]] = payload
        t = payload["totals"]
        summary.append({
            "id": d["id"],
            "code": d["code"],
            "linked_f497_filings": payload["linked_f497_filings"],
            "period_contribution_reports": t["period_contribution_reports"],
            "period_contributions": t["period_contributions"],
            "seven_day": t["seven_day"],
            "ie_reports": t["ie_reports"],
            "ie_period": t["ie_period"],
        })

    return {
        "schema_version": 1,
        "generated_at": as_of,
        "data_as_of": zip_as_of or as_of,
        "election_date": GENERAL_ELECTION_DATE.date().isoformat(),
        "window_start": LATE_MONEY_WINDOW_START.date().isoformat(),
        "window_end": GENERAL_ELECTION_DATE.date().isoformat(),
        "window_days": LATE_REPORTING_PERIOD_DAYS,
        "fppc_reference": "https://www.fppc.ca.gov/siteassets/documents/tad/manuals/campaign/manual_2/Manual_2_Ch_11_Additional_Reports.pdf",
        "source": {
            "publisher": "California Secretary of State — Political Reform Division",
            "dataset": "CAL-ACCESS raw data (daily ZIP)",
            "url": OFFICIAL_ZIP_URL,
            "page": OFFICIAL_PAGE,
            "tables_used": [
                "CVR_CAMPAIGN_DISCLOSURE_CD (F497 covers)",
                "S497_CD (Form 497 late contributions made/received)",
                "S496_CD (Form 496 independent expenditures, window-filtered)",
            ],
            "attribution": "Public CAL-ACCESS data. Not an FPPC or SOS endorsement.",
            "notes": [
                "District linkage: matched candidate committee filer IDs from beachhead roster + ASM/DIST_NO on S497 lines when election date matches the cycle.",
                "Amendments: latest AMEND_ID per FILING_ID; schedule rows deduped by TRAN_ID.",
                "Tracking window: FPPC 90-day election cycle ending on the configured general election date.",
                "Last 24h / 7-day totals use contribution (497) or expenditure (496) dates vs export as-of date.",
                "Street addresses from raw filings are not exported.",
            ],
        },
        "districts": districts_out,
        "summary_report": summary,
    }


def write_late_money_json(bundle: dict, extract_dir: Path) -> Path:
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    dest = LATEST_DIR / "late-money-by-district.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)
        f.write("\n")
    log(f"[ok] wrote {dest}")
    dated = LATEST_DIR / f"late-money-by-district-{extract_dir.name}.json"
    shutil.copy2(dest, dated)
    log(f"[ok] wrote {dated}")
    return dest


def candidate_series_placeholder(receipts: float, spend: float) -> List[float]:
    """Even pace placeholder series from cycle totals (no daily candidate ledger without RCPT/EXPN)."""
    if not spend:
        spend = receipts * 0.5
    # cumulative-looking 8-week pace ending at spend
    return [round(spend * (i + 1) / 8.0, 2) for i in range(8)]


def build_district_payload(
    district: dict,
    cvr_rows: List[dict],
    extract_dir: Path,
    cycle_year: int,
    as_of_iso: str,
) -> dict:
    picked = pick_candidate_committees(cvr_rows, district, cycle_year)
    # gather all filing amends for smry load
    all_amends: Dict[str, int] = {}
    for c in picked["candidates"]:
        for fid, aid in (c.get("filing_amends") or {}).items():
            all_amends[fid] = max(all_amends.get(fid, -1), int(aid))
    smry = load_smry_for_filings(extract_dir, all_amends)

    candidates_out = []
    for c in picked["candidates"]:
        rolled = rollup_candidate_money(c, smry)
        if rolled.get("receipts") is None:
            candidates_out.append({
                "role": rolled["role"],
                "name": rolled["name"],
                "receipts": 0,
                "spend": 0,
                "deltaReceipts": 0,
                "deltaSpend": 0,
                "series": [0] * 8,
                "match_quality": rolled.get("match_quality", "unmatched"),
                "match_reason": rolled.get("match_reason"),
                "provenance": rolled.get("provenance"),
                "live": False,
            })
            continue
        # WoW for candidate committees: not computable from SMRY period totals alone
        candidates_out.append({
            "role": rolled["role"],
            "name": rolled.get("display_name") or rolled["name"],
            "party": rolled.get("party"),
            "committee_name": rolled.get("committee_name"),
            "filer_id": rolled.get("filer_id"),
            "receipts": rolled["receipts"],
            "spend": rolled["spend"],
            "cash_on_hand_latest": rolled.get("cash_on_hand_latest"),
            "deltaReceipts": None,  # not computable without daily ledger
            "deltaSpend": None,
            "series": None,
            "series_note": "Weekly itemized receipts require build_weekly_receipts.py (RCPT_CD / S497)",
            "weekly_receipts_insufficient": True,
            "match_quality": rolled.get("match_quality"),
            "match_score": rolled.get("match_score"),
            "match_reason": rolled.get("match_reason"),
            "provenance": rolled.get("provenance"),
            "live": True,
        })

    cand_names = [c["name"] for c in candidates_out]
    for _kind, person in district_ballot_people(district):
        cand_names.append(person["name"])
    ie_slots = collect_ie_for_district(
        cvr_rows, extract_dir, district["dist_no"], cand_names, cycle_year
    )
    ie_entities = build_ie_entities(ie_slots, datetime.now())

    # District-level match quality
    live_cands = [c for c in candidates_out if c.get("live")]
    strong = [c for c in live_cands if c.get("match_quality") in ("strong", "moderate", "discovered")]
    if strong:
        overall = "live"
    elif live_cands:
        overall = "weak"
    else:
        overall = "unmatched"

    return {
        "id": district["id"],
        "code": district["code"],
        "dist_no": district["dist_no"],
        "focus": district.get("focus"),
        "status": overall,
        "live": overall == "live",
        "candidates": candidates_out,
        "ie": ie_entities[:12],  # top entities
        "notes": [
            "Candidate receipts/spend = sum of Form 460 SMRY line 5 / line 11 period amounts (latest amend per filing) for matched cycle committees.",
            "IE spend = S496 amounts on F496/F465 filings whose cover names an ASM candidate in this district.",
            "Candidate WoW deltas are null — SMRY is period-based; IE WoW uses expenditure dates when present.",
            "Name/district matching is best-effort public-data matching and can mis-attribute similarly named committees.",
        ],
    }


def run_pipeline(extract_dir: Path, zip_path: Optional[Path], skip_download_meta: bool = False) -> Path:
    beach = load_beachheads()
    cycle_year = int(beach.get("cycle_year") or 2026)
    dist_nos = {d["dist_no"] for d in beach["districts"]}
    min_year = cycle_year - 2

    log(f"[cvr] loading ASM disclosures for districts {sorted(dist_nos, key=int)} since {min_year}…")
    cvr_rows = collect_cvr_rows(extract_dir, dist_nos, min_year)
    log(f"[cvr] {len(cvr_rows):,} matching rows")

    as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Prefer ZIP mtime as data-as-of if available
    zip_as_of = None
    if zip_path and zip_path.exists():
        zip_as_of = datetime.fromtimestamp(zip_path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    districts_out = {}
    match_report = []
    for d in beach["districts"]:
        log(f"[district] {d['code']} …")
        payload = build_district_payload(d, cvr_rows, extract_dir, cycle_year, as_of)
        districts_out[d["id"]] = payload
        match_report.append({
            "id": d["id"],
            "code": d["code"],
            "status": payload["status"],
            "candidates": [
                {
                    "name": c["name"],
                    "role": c["role"],
                    "match_quality": c.get("match_quality"),
                    "filer_id": c.get("filer_id"),
                    "committee_name": c.get("committee_name"),
                    "receipts": c.get("receipts"),
                    "spend": c.get("spend"),
                    "live": c.get("live"),
                }
                for c in payload["candidates"]
            ],
            "ie_count": len(payload["ie"]),
        })

    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "schema_version": 1,
        "product": "MajorityIQ",
        "generated_at": as_of,
        "data_as_of": zip_as_of or as_of,
        "source": {
            "publisher": "California Secretary of State — Political Reform Division",
            "dataset": "CAL-ACCESS raw data (daily ZIP)",
            "url": OFFICIAL_ZIP_URL,
            "page": OFFICIAL_PAGE,
            "update_cadence": "Once per day (SOS)",
            "zip_path": str(zip_path) if zip_path else None,
            "extract_dir": str(extract_dir),
            "tables_used": [
                "CVR_CAMPAIGN_DISCLOSURE_CD",
                "SMRY_CD",
                "S496_CD",
                "S497_CD (Form 497 late contributions — see late-money-by-district.json)",
                "FILERNAME_CD (available for enrichment)",
            ],
            "tables_skipped": [
                "RCPT_CD (multi-GB; period totals via SMRY)",
                "EXPN_CD (multi-GB; period totals via SMRY)",
            ],
            "attribution": "Public CAL-ACCESS data. Not an FPPC or SOS endorsement of MajorityIQ.",
        },
        "cycle_year": cycle_year,
        "matching": beach.get("matching_notes"),
        "districts": districts_out,
        "match_report": match_report,
    }

    dest = LATEST_DIR / "money-by-district.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    log(f"[ok] wrote {dest}")

    # dated copy
    date_tag = extract_dir.name
    dated = LATEST_DIR / f"money-by-district-{date_tag}.json"
    shutil.copy2(dest, dated)
    log(f"[ok] wrote {dated}")

    report_path = LATEST_DIR / "match-report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": as_of, "report": match_report}, f, indent=2)
        f.write("\n")

    log("[late-money] building FPPC 90-day Form 497 / 496 rollups…")
    late_bundle = build_late_money_bundle(beach, districts_out, cvr_rows, extract_dir, as_of, zip_as_of)
    write_late_money_json(late_bundle, extract_dir)
    for row in late_bundle["summary_report"]:
        log(
            f"  {row['code']}: F497 filings linked={row['linked_f497_filings']} "
            f"period497={row['period_contribution_reports']} (${row['period_contributions']:,.2f}) "
            f"7d=${row['seven_day']:,.2f} period496={row['ie_reports']} (${row['ie_period']:,.2f})"
        )

    return dest


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="MajorityIQ CAL-ACCESS daily ingest")
    p.add_argument("--skip-download", action="store_true", help="Use existing dated ZIP / extract")
    p.add_argument("--force-download", action="store_true", help="Re-download even if today's ZIP exists")
    p.add_argument("--zip", type=str, default="", help="Path to an existing dbwebexport ZIP")
    p.add_argument("--extract-dir", type=str, default="", help="Path to already-extracted TSV directory")
    p.add_argument("--date", type=str, default="", help="Date tag YYYY-MM-DD (default: today PT)")
    args = p.parse_args(argv)

    date_tag = args.date or today_pt()
    zip_path: Optional[Path] = Path(args.zip) if args.zip else None
    extract_dir: Optional[Path] = Path(args.extract_dir) if args.extract_dir else None

    try:
        if extract_dir and extract_dir.exists():
            log(f"[use] extract-dir {extract_dir}")
        else:
            if not zip_path:
                if args.skip_download:
                    # find newest zip
                    zips = sorted(RAW_DIR.glob("dbwebexport-*.zip"))
                    if not zips:
                        log("ERROR: --skip-download but no ZIP in raw/")
                        return 2
                    zip_path = zips[-1]
                    log(f"[use] newest ZIP {zip_path}")
                else:
                    zip_path = download_zip(force=args.force_download)
                    date_tag = zip_path.stem.replace("dbwebexport-", "")
            extract_dir = extract_needed(zip_path, date_tag=date_tag)

        dest = run_pipeline(extract_dir, zip_path)
        log(f"SUCCESS → {dest}")
        return 0
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
