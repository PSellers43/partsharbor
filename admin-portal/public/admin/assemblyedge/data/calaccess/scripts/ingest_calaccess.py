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


def pick_candidate_committees(
    cvr_rows: List[dict], district: dict, cycle_year: int
) -> Dict[str, Any]:
    """
    For a beachhead district, pick best CTL/CAO F460 committee per configured
    incumbent + known opponents. Also discover other 2026 'for Assembly' CTL
    committees in-district as unmatched/extra opponents.
    """
    dist = district["dist_no"]
    people = [("incumbent", district["incumbent"])] + [
        ("opponent", o) for o in district.get("known_opponents") or []
    ]

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
                "role": "Incumbent" if role == "incumbent" else "Opponent",
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
            "role": "Incumbent" if role == "incumbent" else "Opponent",
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

    # Discover extra 2026 opponent committees not in known list
    extras = []
    for r in cand_filings:
        if r["filer_id"] in claimed_filer_ids:
            continue
        if str(cycle_year) not in r["filer"]:
            continue
        if "FOR ASSEMBLY" not in r["filer"].upper():
            continue
        if r["entity"] not in ("CTL", "CAO"):
            continue
        # skip if looks like ballot measure
        if "BALLOT MEASURE" in r["filer"].upper():
            continue
        extras.append(r)
    # unique by filer
    seen = set()
    for r in sorted(extras, key=lambda x: x["rpt"] or datetime.min, reverse=True):
        if r["filer_id"] in seen or r["filer_id"] in claimed_filer_ids:
            continue
        seen.add(r["filer_id"])
        latest_amend = {}
        for rr in cand_filings:
            if rr["filer_id"] != r["filer_id"]:
                continue
            latest_amend[rr["filing_id"]] = max(latest_amend.get(rr["filing_id"], -1), rr["amend_id"])
        results.append({
            "role": "Opponent",
            "name": r["cand"] or r["filer"],
            "display_name": r["cand"] or r["filer"],
            "party": None,
            "match_quality": "discovered",
            "match_score": 55,
            "match_reason": f"auto-discovered 2026 CTL in AD-{dist}",
            "filer_id": r["filer_id"],
            "committee_name": r["filer"],
            "filing_ids": sorted(latest_amend.keys()),
            "filing_amends": latest_amend,
            "latest_rpt": r["rpt"].isoformat() if r["rpt"] else None,
            "latest_thru": r["thru"].isoformat() if r["thru"] else None,
        })
        claimed_filer_ids.add(r["filer_id"])

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
            "committee_name": rolled.get("committee_name"),
            "filer_id": rolled.get("filer_id"),
            "receipts": rolled["receipts"],
            "spend": rolled["spend"],
            "cash_on_hand_latest": rolled.get("cash_on_hand_latest"),
            "deltaReceipts": None,  # not computable without daily ledger
            "deltaSpend": None,
            "series": candidate_series_placeholder(rolled["receipts"], rolled["spend"]),
            "series_note": "Even-pace illustration from cycle Form 460 totals (not daily cashflow)",
            "match_quality": rolled.get("match_quality"),
            "match_score": rolled.get("match_score"),
            "match_reason": rolled.get("match_reason"),
            "provenance": rolled.get("provenance"),
            "live": True,
        })

    cand_names = [c["name"] for c in candidates_out] + [
        district["incumbent"]["name"]
    ] + [o["name"] for o in district.get("known_opponents") or []]
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
                "S497_CD (reserved / late contributions; not yet in Money rollups)",
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
