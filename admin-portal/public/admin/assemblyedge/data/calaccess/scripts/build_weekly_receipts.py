#!/usr/bin/env python3
"""
Augment money-by-district.json with weekly itemized receipts (and expenditures when available)
from CAL-ACCESS RCPT_CD, EXPN_CD, and S497_CD — streamed from the SOS ZIP without full extract.

Never fabricates weekly values: candidates with insufficient itemized rows get series=null and a flag.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw"
LATEST = ROOT / "latest"
MONEY_PATH = LATEST / "money-by-district.json"

RCPT_MEMBER = "CalAccess/DATA/RCPT_CD.TSV"
EXPN_MEMBER = "CalAccess/DATA/EXPN_CD.TSV"
S497_NAME = "S497_CD.TSV"

WEEKS_CHART = 8


def log(msg: str) -> None:
    print(msg, flush=True)


def parse_cal_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip().split(".")[0]
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def find_zip(explicit: Optional[Path]) -> Optional[Path]:
    if explicit and explicit.exists():
        return explicit
    zips = sorted(RAW_DIR.glob("dbwebexport-*.zip"))
    return zips[-1] if zips else None


def find_s497_tsv(extract_dir: Optional[Path]) -> Optional[Path]:
    if not extract_dir:
        return None
    p = extract_dir / S497_NAME
    return p if p.is_file() else None


def filer_ids_from_money(money: dict) -> Dict[str, Set[str]]:
    """district_id -> filer_ids for live candidates."""
    out: Dict[str, Set[str]] = {}
    for did, dist in (money.get("districts") or {}).items():
        ids: Set[str] = set()
        for c in dist.get("candidates") or []:
            if c.get("live") is False:
                continue
            fid = (c.get("filer_id") or "").strip()
            if fid:
                ids.add(fid)
        if ids:
            out[did] = ids
    return out


def stream_tsv_from_zip(zf: zipfile.ZipFile, member: str, filer_ids: Set[str], date_field: str, amount_field: str) -> dict[str, list[tuple[date, float]]]:
    """filer_id (CMTE_ID) -> list of (date, amount)."""
    buckets: dict[str, list[tuple[date, float]]] = defaultdict(list)
    try:
        info = zf.getinfo(member)
    except KeyError:
        alt = next((n for n in zf.namelist() if n.upper().endswith(member.split("/")[-1].upper())), None)
        if not alt:
            log(f"[skip] {member} not in ZIP")
            return buckets
        member = alt
    log(f"[stream] {member} ({info.file_size/1e9:.2f} GB) for {len(filer_ids)} filers…")
    with zf.open(member) as raw:
        header = raw.readline().decode("utf-8", errors="replace").strip().split("\t")
        id_field = "CMTE_ID" if "CMTE_ID" in header else "FILER_ID"
        try:
            fi = header.index(id_field)
            di = header.index(date_field)
            ai = header.index(amount_field)
        except ValueError as e:
            log(f"[skip] column missing in {member}: {e}")
            return buckets
        for line in raw:
            parts = line.decode("utf-8", errors="replace").rstrip("\n").split("\t")
            if len(parts) <= max(fi, di, ai):
                continue
            fid = parts[fi].strip()
            if fid not in filer_ids:
                continue
            dt = parse_cal_date(parts[di])
            if not dt:
                continue
            try:
                amt = float(parts[ai] or 0)
            except ValueError:
                amt = 0.0
            if amt <= 0:
                continue
            buckets[fid].append((dt, amt))
    return buckets


def load_s497_receipts(path: Path, filer_ids: Set[str]) -> dict[str, list[tuple[date, float]]]:
    buckets: dict[str, list[tuple[date, float]]] = defaultdict(list)
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            fid = (row.get("FILER_ID") or "").strip()
            if fid not in filer_ids:
                continue
            dt = parse_cal_date(row.get("RCPT_DATE") or row.get("CONTRIB_DATE") or row.get("RPT_DATE"))
            if not dt:
                continue
            try:
                amt = float(row.get("AMOUNT") or 0)
            except ValueError:
                amt = 0.0
            if amt <= 0:
                continue
            buckets[fid].append((dt, amt))
    return buckets


def rollup_weekly(events: list[tuple[date, float]], weeks: int = WEEKS_CHART) -> tuple[list[float], Optional[date], int]:
    if not events:
        return [], None, 0
    by_week: dict[date, float] = defaultdict(float)
    max_day: Optional[date] = None
    for dt, amt in events:
        by_week[week_start_monday(dt)] += amt
        if max_day is None or dt > max_day:
            max_day = dt
    ordered = sorted(by_week.items())
    if len(ordered) > weeks:
        ordered = ordered[-weeks:]
    series = [round(v, 2) for _, v in ordered]
    return series, max_day, len(events)


def augment_money(
    money: dict,
    rcpt: dict[str, list[tuple[date, float]]],
    expn: dict[str, list[tuple[date, float]]],
    s497: dict[str, list[tuple[date, float]]],
) -> dict:
    all_filer_events: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for src in (rcpt, s497):
        for fid, ev in src.items():
            all_filer_events[fid].extend(ev)

    last_filed_global: Optional[date] = None
    for dist in (money.get("districts") or {}).values():
        for c in dist.get("candidates") or []:
            if c.get("live") is False:
                continue
            fid = (c.get("filer_id") or "").strip()
            rcpt_ev = list(all_filer_events.get(fid) or [])
            expn_ev = list(expn.get(fid) or [])
            series, last_day, n_rows = rollup_weekly(rcpt_ev)
            exp_series, exp_last, exp_n = rollup_weekly(expn_ev) if expn_ev else ([], None, 0)
            if last_day and (last_filed_global is None or last_day > last_filed_global):
                last_filed_global = last_day
            if n_rows >= 2 and series:
                c["series"] = series
                c["series_note"] = None
                c["weekly_receipts_insufficient"] = False
                c["weekly_receipts_row_count"] = n_rows
                c["weekly_receipts_last_day"] = last_day.isoformat() if last_day else None
                if exp_series and exp_n >= 2:
                    c["weekly_expenditure_series"] = exp_series
                    c["weekly_expenditures_last_day"] = exp_last.isoformat() if exp_last else None
            else:
                c["series"] = None
                c["series_note"] = "Not enough itemized filings for weekly chart"
                c["weekly_receipts_insufficient"] = True
                c["weekly_receipts_row_count"] = n_rows

    meta = money.setdefault("weekly_itemized", {})
    meta["built_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta["last_filed_day"] = last_filed_global.isoformat() if last_filed_global else None
    meta["weeks_chart"] = WEEKS_CHART
    meta["sources"] = ["RCPT_CD (Schedule A)", "S497_CD (late contributions)", "EXPN_CD (Schedule E, when available)"]
    meta["label"] = (
        f"Weekly itemized receipts (CAL-ACCESS, last filed day {last_filed_global.isoformat() if last_filed_global else '—'})"
    )
    return money


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Add weekly CAL-ACCESS itemized series to money JSON")
    p.add_argument("--zip", type=str, default="", help="dbwebexport.zip path")
    p.add_argument("--extract-dir", type=str, default="", help="Optional extract dir with S497_CD.TSV")
    p.add_argument("--skip-rcpt", action="store_true", help="Do not stream RCPT (keep flags only)")
    args = p.parse_args(argv)

    if not MONEY_PATH.exists():
        log(f"ERROR: missing {MONEY_PATH}")
        return 2

    money = json.loads(MONEY_PATH.read_text(encoding="utf-8"))
    filer_by_dist = filer_ids_from_money(money)
    all_filers: Set[str] = set()
    for s in filer_by_dist.values():
        all_filers |= s
    if not all_filers:
        log("[warn] no filer IDs in money JSON — nothing to do")
        return 0

    zip_path = find_zip(Path(args.zip) if args.zip else None)
    extract_dir = Path(args.extract_dir) if args.extract_dir else None
    if not extract_dir and money.get("source", {}).get("extract_dir"):
        extract_dir = Path(money["source"]["extract_dir"])

    rcpt: dict[str, list[tuple[date, float]]] = defaultdict(list)
    expn: dict[str, list[tuple[date, float]]] = defaultdict(list)
    s497: dict[str, list[tuple[date, float]]] = defaultdict(list)

    s497_path = find_s497_tsv(extract_dir)
    if s497_path:
        log(f"[s497] {s497_path}")
        s497 = load_s497_receipts(s497_path, all_filers)
    else:
        log("[s497] not found — RCPT-only unless ZIP contains S497 in extract")

    if not args.skip_rcpt and zip_path:
        with zipfile.ZipFile(zip_path, "r") as zf:
            rcpt = stream_tsv_from_zip(zf, RCPT_MEMBER, all_filers, "RCPT_DATE", "AMOUNT")
            expn = stream_tsv_from_zip(zf, EXPN_MEMBER, all_filers, "EXPN_DATE", "AMOUNT")
    elif not zip_path:
        log("[warn] no CAL-ACCESS ZIP — weekly receipts not updated (insufficient data flags only)")

    money = augment_money(money, rcpt, expn, s497)
    MONEY_PATH.write_text(json.dumps(money, indent=2) + "\n", encoding="utf-8")
    log(f"[ok] updated {MONEY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
