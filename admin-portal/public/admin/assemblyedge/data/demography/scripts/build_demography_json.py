#!/usr/bin/env python3
"""Build MajorityIQ demography + voter-registration JSON for beachhead ADs.

Sources (free / public):
  - U.S. Census Bureau ACS 5-year (via Census Reporter API mirror, no key)
  - CA Secretary of State Report of Registration — Registration by State Assembly District (XLSX)

Outputs:
  ../latest/demography-by-district.json
  ../latest/demography-by-district-YYYY-MM-DD.json

Optional: set CENSUS_API_KEY to refresh ACS directly from api.census.gov instead of Census Reporter.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "latest"
RAW = ROOT / "raw"

BEACHHEADS = {
    "ad-7": 7,
    "ad-27": 27,
    "ad-36": 36,
    "ad-47": 47,
    "ad-58": 58,
    "ad-74": 74,
}

DEFAULT_ROR_XLSX = (
    "https://elections.cdn.sos.ca.gov/ror/60day-gen-2026/assembly.xlsx"
)
CENSUS_REPORTER = "https://api.censusreporter.org/1.0/data/show/latest"
CENSUS_API = "https://api.census.gov/data/2023/acs/acs5"

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def fetch_bytes(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "MajorityIQ-demography-build/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sldl_geoid(dist_no: int) -> str:
    return f"62000US06{dist_no:03d}"


def pct(part: float, whole: float) -> float | None:
    if whole is None or whole <= 0 or part is None:
        return None
    return round(100.0 * part / whole, 1)


def census_var_to_cr_key(var: str) -> str:
    """Map Census API variable ids (B01001_001E) to Census Reporter keys (B01001001)."""
    if var.endswith("E"):
        var = var[:-1]
    return var.replace("_", "")


def normalize_estimates(est: dict) -> dict:
    """Accept either Census API (_E suffix) or Census Reporter (no suffix) keys."""
    if not est:
        return {}
    sample = next(iter(est))
    if "_" in sample or sample.endswith("E"):
        return est
    out = {}
    for k, v in est.items():
        # B01001001 -> B01001_001E
        m = re.match(r"^([A-Z]\d{5})(\d{3})$", k)
        if m:
            out[f"{m.group(1)}_{m.group(2)}E"] = v
        else:
            out[k] = v
    return out


def sum_vars(est: dict, keys: list[str]) -> int:
    total = 0
    for k in keys:
        v = est.get(k)
        if v is None:
            continue
        try:
            total += int(v)
        except (TypeError, ValueError):
            pass
    return total


def age_bands_from_b01001(est: dict) -> list[dict]:
    pop = int(est.get("B01001_001E") or 0)
    if pop <= 0:
        return []
    bands = [
        (
            "Under 18",
            sum_vars(
                est,
                [
                    "B01001_003E",
                    "B01001_004E",
                    "B01001_005E",
                    "B01001_006E",
                    "B01001_027E",
                    "B01001_028E",
                    "B01001_029E",
                    "B01001_030E",
                ],
            ),
        ),
        (
            "18–34",
            sum_vars(
                est,
                [
                    "B01001_007E",
                    "B01001_008E",
                    "B01001_009E",
                    "B01001_010E",
                    "B01001_011E",
                    "B01001_012E",
                    "B01001_031E",
                    "B01001_032E",
                    "B01001_033E",
                    "B01001_034E",
                    "B01001_035E",
                    "B01001_036E",
                ],
            ),
        ),
        (
            "35–54",
            sum_vars(
                est,
                [
                    "B01001_013E",
                    "B01001_014E",
                    "B01001_015E",
                    "B01001_016E",
                    "B01001_037E",
                    "B01001_038E",
                    "B01001_039E",
                    "B01001_040E",
                ],
            ),
        ),
        (
            "55–64",
            sum_vars(
                est,
                [
                    "B01001_017E",
                    "B01001_018E",
                    "B01001_019E",
                    "B01001_041E",
                    "B01001_042E",
                    "B01001_043E",
                ],
            ),
        ),
        (
            "65+",
            sum_vars(
                est,
                [
                    "B01001_020E",
                    "B01001_021E",
                    "B01001_022E",
                    "B01001_023E",
                    "B01001_024E",
                    "B01001_025E",
                    "B01001_044E",
                    "B01001_045E",
                    "B01001_046E",
                    "B01001_047E",
                    "B01001_048E",
                    "B01001_049E",
                ],
            ),
        ),
    ]
    out = []
    for label, count in bands:
        p = pct(count, pop)
        if p is not None:
            out.append({"label": label, "count": count, "pct": p})
    return out


def race_ethnicity_from_b03002_census_api(est: dict) -> list[dict]:
    total = int(est.get("B03002_001E") or 0)
    if total <= 0:
        return []
    hispanic = int(est.get("B03002_003E") or 0)
    nh_white = int(est.get("B03002_005E") or 0)
    nh_black = int(est.get("B03002_008E") or 0)
    nh_asian = int(est.get("B03002_016E") or 0)
    nh_other = max(0, total - hispanic - nh_white - nh_black - nh_asian)
    rows = [
        ("Hispanic / Latino (any race)", hispanic),
        ("White (non-Hispanic)", nh_white),
        ("Black (non-Hispanic)", nh_black),
        ("Asian (non-Hispanic)", nh_asian),
        ("Other / multiracial (non-Hispanic)", nh_other),
    ]
    return [
        {"label": label, "count": count, "pct": pct(count, total)}
        for label, count in rows
        if pct(count, total) is not None
    ]


def race_ethnicity_from_b03002_cr(est: dict) -> list[dict]:
    """Census Reporter uses sequential B03002xxx column ids (not Census API _005E suffixes)."""
    total = int(est.get("B03002001") or 0)
    if total <= 0:
        return []
    hispanic = int(est.get("B03002012") or 0)
    nh_total = int(est.get("B03002002") or 0)
    nh_white = int(est.get("B03002003") or 0)
    nh_black = int(est.get("B03002004") or 0)
    nh_asian = int(est.get("B03002006") or 0)
    nh_other = max(0, nh_total - nh_white - nh_black - nh_asian)
    rows = [
        ("Hispanic / Latino (any race)", hispanic),
        ("White (non-Hispanic)", nh_white),
        ("Black (non-Hispanic)", nh_black),
        ("Asian (non-Hispanic)", nh_asian),
        ("Other / multiracial (non-Hispanic)", nh_other),
    ]
    return [
        {"label": label, "count": count, "pct": pct(count, total)}
        for label, count in rows
        if pct(count, total) is not None
    ]


def tenure_from_b25003(est: dict) -> dict | None:
    occupied = int(est.get("B25003_001E") or 0)
    if occupied <= 0:
        return None
    owner = int(est.get("B25003_002E") or 0)
    renter = int(est.get("B25003_003E") or 0)
    return {
        "owner_count": owner,
        "renter_count": renter,
        "owner_pct": pct(owner, occupied),
        "renter_pct": pct(renter, occupied),
    }


def acs_from_census_reporter(dist_no: int) -> dict:
    geo = sldl_geoid(dist_no)
    tables = "B01001,B03002,B19013,B25003"
    url = f"{CENSUS_REPORTER}?table_ids={tables}&geo_ids={geo}"
    raw = json.loads(fetch_bytes(url).decode("utf-8"))
    if raw.get("error"):
        raise RuntimeError(f"Census Reporter: {raw['error']}")
    release = raw.get("release") or {}
    est_root = raw.get("data") or {}
    geo_block = est_root.get(geo) or est_root
    b01_raw = (geo_block.get("B01001") or {}).get("estimate") or {}
    b03_raw = (geo_block.get("B03002") or {}).get("estimate") or {}
    b01 = normalize_estimates(b01_raw)
    b19 = normalize_estimates((geo_block.get("B19013") or {}).get("estimate") or {})
    b25 = normalize_estimates((geo_block.get("B25003") or {}).get("estimate") or {})
    pop = int(b01.get("B01001_001E") or 0)
    med_income = b19.get("B19013_001E")
    try:
        med_income = int(med_income) if med_income is not None else None
    except (TypeError, ValueError):
        med_income = None
    return {
        "population": pop,
        "median_household_income": med_income,
        "age_bands": age_bands_from_b01001(b01),
        "race_ethnicity": race_ethnicity_from_b03002_cr(b03_raw),
        "housing_tenure": tenure_from_b25003(b25),
        "geo_id": geo,
        "release_id": release.get("id"),
        "release_name": release.get("name"),
        "release_years": release.get("years"),
        "source_label": "U.S. Census Bureau ACS 5-year (via Census Reporter API)",
        "source_url": "https://censusreporter.org/",
        "method": "census_reporter",
    }


def acs_from_census_api(dist_no: int, api_key: str) -> dict:
    geo = sldl_geoid(dist_no)
    # Census API uses lower chamber code 620 in for= clause as district number zero-padded
    var_list = [
        "B01001_001E",
        "B01001_003E",
        "B01001_004E",
        "B01001_005E",
        "B01001_006E",
        "B01001_007E",
        "B01001_008E",
        "B01001_009E",
        "B01001_010E",
        "B01001_011E",
        "B01001_012E",
        "B01001_013E",
        "B01001_014E",
        "B01001_015E",
        "B01001_016E",
        "B01001_017E",
        "B01001_018E",
        "B01001_019E",
        "B01001_020E",
        "B01001_021E",
        "B01001_022E",
        "B01001_023E",
        "B01001_024E",
        "B01001_025E",
        "B01001_027E",
        "B01001_028E",
        "B01001_029E",
        "B01001_030E",
        "B01001_031E",
        "B01001_032E",
        "B01001_033E",
        "B01001_034E",
        "B01001_035E",
        "B01001_036E",
        "B01001_037E",
        "B01001_038E",
        "B01001_039E",
        "B01001_040E",
        "B01001_041E",
        "B01001_042E",
        "B01001_043E",
        "B01001_044E",
        "B01001_045E",
        "B01001_046E",
        "B01001_047E",
        "B01001_048E",
        "B01001_049E",
        "B03002_001E",
        "B03002_005E",
        "B03002_008E",
        "B03002_003E",
        "B03002_016E",
        "B19013_001E",
        "B25003_001E",
        "B25003_002E",
        "B25003_003E",
    ]
    dist = f"{dist_no:03d}"
    url = (
        f"{CENSUS_API}?get={','.join(var_list)}"
        f"&for=state%20legislative%20district%20(lower%20chamber):{dist}"
        f"&in=state:06&key={urllib.parse.quote(api_key)}"
    )
    rows = json.loads(fetch_bytes(url).decode("utf-8"))
    if not rows or not isinstance(rows, list) or rows[0][0] == "error":
        raise RuntimeError(f"Census API error for AD-{dist_no}: {rows}")
    header = rows[0]
    values = rows[1]
    est = dict(zip(header, values))
    pop = int(est.get("B01001_001E") or 0)
    med_income = est.get("B19013_001E")
    try:
        med_income = int(med_income) if med_income is not None else None
    except (TypeError, ValueError):
        med_income = None
    return {
        "population": pop,
        "median_household_income": med_income,
        "age_bands": age_bands_from_b01001(est),
        "race_ethnicity": race_ethnicity_from_b03002_census_api(est),
        "housing_tenure": tenure_from_b25003(est),
        "geo_id": geo,
        "release_id": "acs2023_5yr",
        "release_name": "ACS 2023 5-year",
        "release_years": "2019-2023",
        "source_label": "U.S. Census Bureau ACS 5-year (Census Data API)",
        "source_url": "https://api.census.gov/",
        "method": "census_api",
    }


def _col_letter(cell_ref: str) -> int:
    m = re.match(r"^([A-Z]+)", cell_ref)
    if not m:
        return 0
    letters = m.group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def read_xlsx_rows(path: Path) -> list[tuple]:
    """Minimal XLSX reader (shared strings + sheet1)."""
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                parts = [t.text or "" for t in si.findall(".//m:t", NS)]
                shared.append("".join(parts))
        sheet_name = "xl/worksheets/sheet1.xml"
        for name in zf.namelist():
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                sheet_name = name
                break
        sheet = ET.fromstring(zf.read(sheet_name))
        rows_out: list[tuple] = []
        for row in sheet.findall("m:sheetData/m:row", NS):
            cells = {}
            for c in row.findall("m:c", NS):
                ref = c.get("r", "A1")
                col = _col_letter(ref)
                t = c.get("t")
                v_el = c.find("m:v", NS)
                if v_el is None or v_el.text is None:
                    val = None
                elif t == "s":
                    val = shared[int(v_el.text)]
                else:
                    val = v_el.text
                    try:
                        if "." in val:
                            val = float(val)
                        else:
                            val = int(val)
                    except (TypeError, ValueError):
                        pass
                cells[col] = val
            if not cells:
                rows_out.append(tuple())
                continue
            max_col = max(cells)
            row_tuple = tuple(cells.get(i) for i in range(max_col + 1))
            rows_out.append(row_tuple)
        return rows_out


def parse_registration_xlsx(path: Path) -> dict[int, dict]:
    rows = read_xlsx_rows(path)
    targets = set(BEACHHEADS.values())
    current: int | None = None
    out: dict[int, dict] = {}
    for row in rows:
        if not row:
            continue
        c0 = row[0] if len(row) > 0 else None
        if isinstance(c0, str) and c0.startswith("State Assembly"):
            try:
                current = int(c0.split()[-1])
            except ValueError:
                current = None
            continue
        if c0 == "District Total" and current in targets:
            # Col layout from SOS sheet: total, D, R, AIP, Grn, Lib, PF, Unknown, Other, NPP
            total = row[2] if len(row) > 2 else None
            dem = row[3] if len(row) > 3 else None
            rep = row[4] if len(row) > 4 else None
            npp = row[11] if len(row) > 11 else None
            other = 0
            for idx in range(5, 11):
                if len(row) > idx and isinstance(row[idx], (int, float)):
                    other += int(row[idx])
            try:
                total_i = int(total)
            except (TypeError, ValueError):
                continue

            def party_row(pid: str, label: str, count) -> dict:
                try:
                    c = int(count)
                except (TypeError, ValueError):
                    c = 0
                return {
                    "id": pid,
                    "label": label,
                    "count": c,
                    "pct": pct(c, total_i),
                }

            parties = [
                party_row("dem", "Democratic", dem),
                party_row("rep", "Republican", rep),
                party_row("npp", "No party preference", npp),
                party_row("other", "Other / minor", other),
            ]
            out[current] = {"total": total_i, "parties": parties}
    return out


def load_registration(source_url: str, raw_path: Path | None) -> tuple[dict[int, dict], dict]:
    if raw_path and raw_path.is_file():
        data_path = raw_path
        fetched_from = str(raw_path)
    else:
        RAW.mkdir(parents=True, exist_ok=True)
        data_path = RAW / "assembly-registration.xlsx"
        data_path.write_bytes(fetch_bytes(source_url))
        fetched_from = source_url
    parsed = parse_registration_xlsx(data_path)
    meta = {
        "source_label": "CA Secretary of State Report of Registration",
        "source_url": source_url,
        "raw_file": data_path.name,
        "fetched_from": fetched_from,
        "as_of": "2026-09-04",
        "as_of_note": "60-day Report of Registration before Nov 3, 2026 general (Assembly district worksheet)",
    }
    return parsed, meta


def build(use_census_api_key: str | None, ror_url: str, ror_file: Path | None) -> dict:
    reg_by_dist, reg_meta = load_registration(ror_url, ror_file)
    districts = []
    gaps = []
    for dist_id, dist_no in BEACHHEADS.items():
        acs = None
        acs_err = None
        try:
            if use_census_api_key:
                acs = acs_from_census_api(dist_no, use_census_api_key)
            else:
                acs = acs_from_census_reporter(dist_no)
        except Exception as exc:  # noqa: BLE001 — surface per-district gaps in JSON
            acs_err = str(exc)
            gaps.append(f"{dist_id} ACS: {acs_err}")
        reg = reg_by_dist.get(dist_no)
        if not reg:
            gaps.append(f"{dist_id} registration: missing District Total row")
        districts.append(
            {
                "id": dist_id,
                "code": f"AD-{dist_no}",
                "acs": acs,
                "acs_error": acs_err,
                "registration": reg,
            }
        )
    now = datetime.now(timezone.utc).astimezone()
    payload = {
        "schema_version": 1,
        "updated_at": now.isoformat(timespec="seconds"),
        "built_on": date.today().isoformat(),
        "sources": {
            "acs": {
                "default_method": "census_reporter",
                "census_reporter_url": CENSUS_REPORTER,
                "census_api_url": CENSUS_API,
                "census_api_key_env": "CENSUS_API_KEY",
                "tables": ["B01001", "B03002", "B19013", "B25003"],
                "geography": "State legislative district (lower chamber) — CA Assembly (CRC 2020 lines)",
            },
            "registration": reg_meta,
        },
        "gaps": gaps,
        "districts": districts,
    }
    return payload


def write_outputs(payload: dict) -> None:
    LATEST.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    dated = LATEST / f"demography-by-district-{stamp}.json"
    latest = LATEST / "demography-by-district.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    dated.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(f"Wrote {latest} ({len(payload['districts'])} districts)")
    if payload.get("gaps"):
        print("Gaps:", "; ".join(payload["gaps"]), file=sys.stderr)


def main() -> int:
    import argparse
    import os

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--ror-url",
        default=DEFAULT_ROR_XLSX,
        help="SOS Assembly district registration XLSX URL",
    )
    ap.add_argument(
        "--ror-file",
        type=Path,
        default=None,
        help="Use a local XLSX instead of downloading",
    )
    ap.add_argument(
        "--census-api",
        action="store_true",
        help="Use Census Data API (requires CENSUS_API_KEY) instead of Census Reporter",
    )
    args = ap.parse_args()
    api_key = os.environ.get("CENSUS_API_KEY") if args.census_api else None
    if args.census_api and not api_key:
        print("CENSUS_API_KEY is required with --census-api", file=sys.stderr)
        return 2
    try:
        payload = build(api_key, args.ror_url, args.ror_file)
    except urllib.error.URLError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    write_outputs(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
