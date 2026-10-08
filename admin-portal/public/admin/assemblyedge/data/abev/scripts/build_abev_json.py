#!/usr/bin/env python3
"""Build MajorityIQ ballot-return (ABEV-style) JSON for beachhead Assembly districts.

Sources (free / public):
  - UC Berkeley Statewide Database (SWDB) Statement of Vote by SR precinct (addist filter)
  - SWDB All_VBM voter-status files (mail ballot voters who returned), aggregated to AD
  - CA SOS Report of Registration (optional denominator via demography JSON)
  - CA SOS VoteCal VBM statistics PDF (optional live-cycle probe — county-level only)

Live 2026 Assembly-district returns are usually unavailable until counties/SOS publish feeds;
when missing, JSON includes explicit gaps and historical baselines (2024 g24, 2022 g22).

Outputs:
  ../latest/abev-by-district.json
  ../latest/abev-by-district-YYYY-MM-DD.json
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "latest"
DEMOGRAPHY = ROOT.parent / "demography" / "latest" / "demography-by-district.json"

BEACHHEADS = {
    "ad-7": 7,
    "ad-27": 27,
    "ad-36": 36,
    "ad-47": 47,
    "ad-58": 58,
    "ad-74": 74,
}

# Counties that intersect beachhead ADs (from intra-district map build)
COUNTIES_BY_AD: dict[str, list[int]] = {
    "7": [67, 61],
    "27": [19, 39, 47],
    "36": [25, 65, 71],
    "47": [65, 71],
    "58": [65, 71],
    "74": [59, 73],
}

ELECTIONS = {
    "g24": {
        "label": "2024 General (Nov 5, 2024)",
        "election_code": "g24",
        "sov_template": "https://statewidedatabase.org/pub/data/G24/c{cid:03d}/c{cid:03d}_g24_sov_data_by_g24_srprec.csv",
        "vbm_zip": "https://statewidedatabase.org/pub/data/G24/state/state_g24_All_VBM_by_g24_srprec.zip",
    },
    "g22": {
        "label": "2022 General (Nov 8, 2022)",
        "election_code": "g22",
        "sov_template": "https://statewidedatabase.org/pub/data/G22/c{cid:03d}/c{cid:03d}_g22_sov_data_by_g22_srprec.csv",
        "vbm_zip": "https://statewidedatabase.org/pub/data/G22/state/state_g22_All_VBM_by_g22_srprec.zip",
    },
}

LIVE_BSR_XLSX = (
    "https://elections.cdn.sos.ca.gov/statewide-elections/2026-general/bsr-statistics.xlsx"
)
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

CA_COUNTY_NAME_TO_FIPS = {
    "alameda": 1,
    "alpine": 3,
    "amador": 5,
    "butte": 7,
    "calaveras": 9,
    "colusa": 11,
    "contra costa": 13,
    "del norte": 15,
    "el dorado": 17,
    "fresno": 19,
    "glenn": 21,
    "humboldt": 23,
    "imperial": 25,
    "inyo": 27,
    "kern": 29,
    "kings": 31,
    "lake": 33,
    "lassen": 35,
    "los angeles": 37,
    "madera": 39,
    "marin": 41,
    "mariposa": 43,
    "mendocino": 45,
    "merced": 47,
    "modoc": 49,
    "mono": 51,
    "monterey": 53,
    "napa": 55,
    "nevada": 57,
    "orange": 59,
    "placer": 61,
    "plumas": 63,
    "riverside": 65,
    "sacramento": 67,
    "san benito": 69,
    "san bernardino": 71,
    "san diego": 73,
    "san francisco": 75,
    "san joaquin": 77,
    "san luis obispo": 79,
    "san mateo": 81,
    "santa barbara": 83,
    "santa clara": 85,
    "santa cruz": 87,
    "shasta": 89,
    "sierra": 91,
    "siskiyou": 93,
    "solano": 95,
    "sonoma": 97,
    "stanislaus": 99,
    "sutter": 101,
    "tehama": 103,
    "trinity": 105,
    "tulare": 107,
    "tuolumne": 109,
    "ventura": 111,
    "yolo": 113,
    "yuba": 115,
}

PARTY_IDS = [
    ("dem", "DEM", "Democratic"),
    ("rep", "REP", "Republican"),
    ("npp", "DCL", "No party preference"),
    ("aip", "AIP", "American Independent"),
    ("grn", "GRN", "Green"),
    ("lib", "LIB", "Libertarian"),
    ("other", None, "Other / minor"),
]


def fetch_bytes(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "MajorityIQ-abev-build/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def num(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def pct(part: float, whole: float) -> float | None:
    if whole is None or whole <= 0:
        return None
    return round(100.0 * part / whole, 2)


def load_sov_addist_map(election_key: str, county_ids: set[int]) -> dict[tuple[str, str], int]:
    """(fips, srprec) -> assembly district number."""
    tmpl = ELECTIONS[election_key]["sov_template"]
    out: dict[tuple[str, str], int] = {}
    for cid in sorted(county_ids):
        url = tmpl.format(cid=cid)
        try:
            text = fetch_bytes(url).decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"  warn: SOV skip county {cid:03d}: {exc}", file=sys.stderr)
            continue
        reader = csv.DictReader(io.StringIO(text))
        fips_key = f"06{cid:03d}"
        for row in reader:
            addist = int(num(row.get("addist") or row.get("ADDIST") or 0))
            if addist not in BEACHHEADS.values():
                continue
            srprec = (row.get("srprec") or row.get("SRPREC") or "").strip().strip('"')
            if not srprec:
                continue
            out[(fips_key, srprec)] = addist
    return out


def aggregate_sov(election_key: str, county_ids: set[int]) -> dict[int, dict]:
    """Per AD: registration and vote totals from SOV (15-day ROR snapshot in SWDB)."""
    tmpl = ELECTIONS[election_key]["sov_template"]
    acc: dict[int, dict] = defaultdict(
        lambda: {
            "totreg": 0.0,
            "totvote": 0.0,
            "absvote": 0.0,
            "demreg": 0.0,
            "repreg": 0.0,
            "dclreg": 0.0,
        }
    )
    for cid in sorted(county_ids):
        url = tmpl.format(cid=cid)
        try:
            text = fetch_bytes(url).decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"  warn: SOV agg skip county {cid:03d}: {exc}", file=sys.stderr)
            continue
        for row in csv.DictReader(io.StringIO(text)):
            addist = int(num(row.get("addist") or 0))
            if addist not in BEACHHEADS.values():
                continue
            acc[addist]["totreg"] += num(row.get("TOTREG"))
            acc[addist]["totvote"] += num(row.get("TOTVOTE"))
            acc[addist]["absvote"] += num(row.get("ABSVOTE"))
            acc[addist]["demreg"] += num(row.get("DEMREG"))
            acc[addist]["repreg"] += num(row.get("REPREG"))
            acc[addist]["dclreg"] += num(row.get("DCLREG"))
    return acc


def aggregate_vbm(election_key: str, addist_map: dict[tuple[str, str], int]) -> dict[int, dict]:
    """Per AD: mail ballot returns + party mix from SWDB All_VBM."""
    url = ELECTIONS[election_key]["vbm_zip"]
    raw = fetch_bytes(url)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
    text = zf.read(csv_name).decode("utf-8", errors="replace")

    acc: dict[int, dict] = defaultdict(
        lambda: {
            "returned": 0.0,
            "parties": defaultdict(float),
            "srprec_rows": 0,
        }
    )
    for row in csv.DictReader(io.StringIO(text)):
        fips = (row.get("FIPS") or "").strip()
        srprec = (row.get("SRPREC") or "").strip()
        key = (fips, srprec)
        addist = addist_map.get(key)
        if addist is None:
            continue
        returned = num(row.get("TOTREG_R"))
        acc[addist]["returned"] += returned
        acc[addist]["srprec_rows"] += 1
        dem = num(row.get("DEM"))
        rep = num(row.get("REP"))
        dcl = num(row.get("DCL"))
        other = returned - dem - rep - dcl
        if other < 0:
            other = 0.0
        acc[addist]["parties"]["dem"] += dem
        acc[addist]["parties"]["rep"] += rep
        acc[addist]["parties"]["npp"] += dcl
        acc[addist]["parties"]["other"] += other
    return acc


def party_rows(party_counts: dict, total: float) -> list[dict]:
    rows = []
    for pid, _col, label in PARTY_IDS:
        if pid == "other":
            count = party_counts.get("other", 0.0)
        else:
            count = party_counts.get(pid, 0.0)
        rows.append(
            {
                "id": pid,
                "label": label,
                "count": int(round(count)),
                "pct": pct(count, total),
            }
        )
    return rows


def load_ror_registration() -> dict[str, int]:
    if not DEMOGRAPHY.is_file():
        return {}
    data = json.loads(DEMOGRAPHY.read_text(encoding="utf-8"))
    out = {}
    for d in data.get("districts") or []:
        reg = (d.get("registration") or {}).get("total")
        if reg is not None:
            out[d["id"]] = int(reg)
    return out


def _col_letter(cell_ref: str) -> int:
    m = re.match(r"^([A-Z]+)", cell_ref or "")
    if not m:
        return 0
    letters = m.group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def read_xlsx_rows(raw: bytes) -> list[tuple]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", XLSX_NS):
                parts = [t.text or "" for t in si.findall(".//m:t", XLSX_NS)]
                shared.append("".join(parts))
        sheet_name = next(
            (n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),
            "xl/worksheets/sheet1.xml",
        )
        sheet = ET.fromstring(zf.read(sheet_name))
        rows_out: list[tuple] = []
        for row in sheet.findall("m:sheetData/m:row", XLSX_NS):
            cells: dict[int, object] = {}
            for c in row.findall("m:c", XLSX_NS):
                ref = c.get("r", "A1")
                col = _col_letter(ref)
                t = c.get("t")
                v_el = c.find("m:v", XLSX_NS)
                if v_el is None or v_el.text is None:
                    val = None
                elif t == "s":
                    val = shared[int(v_el.text)]
                else:
                    val = v_el.text
                    try:
                        val = float(val) if "." in str(val) else int(val)
                    except (TypeError, ValueError):
                        pass
                cells[col] = val
            if not cells:
                rows_out.append(tuple())
                continue
            max_col = max(cells)
            rows_out.append(tuple(cells.get(i) for i in range(max_col + 1)))
        return rows_out


def parse_bsr_counties(raw: bytes) -> tuple[list[dict], str | None]:
    """Return county rows from SOS bsr-statistics.xlsx (county-level mail ballot status)."""
    rows = read_xlsx_rows(raw)
    header_idx = None
    for i, row in enumerate(rows):
        if not row:
            continue
        joined = " ".join(str(c or "") for c in row).lower()
        if "county" in joined and ("return" in joined or "received" in joined or "ballot" in joined):
            header_idx = i
            break
    if header_idx is None:
        header_idx = 0
    header = [str(c or "").strip().lower() for c in rows[header_idx]]
    col_county = next((i for i, h in enumerate(header) if "county" in h), 0)
    col_returned = next(
        (i for i, h in enumerate(header) if "return" in h or "received" in h or "complete" in h),
        None,
    )
    col_issued = next((i for i, h in enumerate(header) if "issue" in h or "sent" in h or "mail" in h), None)
    col_as_of = next((i for i, h in enumerate(header) if "as of" in h or "date" in h), None)
    out: list[dict] = []
    as_of = None
    for row in rows[header_idx + 1 :]:
        if not row or len(row) <= col_county:
            continue
        name_raw = row[col_county]
        if not name_raw or not isinstance(name_raw, str):
            continue
        name_key = name_raw.strip().lower().replace(" county", "")
        fips = CA_COUNTY_NAME_TO_FIPS.get(name_key)
        if fips is None:
            continue
        returned = num(row[col_returned]) if col_returned is not None and len(row) > col_returned else 0
        issued = num(row[col_issued]) if col_issued is not None and len(row) > col_issued else None
        if returned <= 0 and (issued is None or issued <= 0):
            continue
        if col_as_of is not None and len(row) > col_as_of and row[col_as_of]:
            as_of = str(row[col_as_of]).strip()
        out.append(
            {
                "fips": fips,
                "name": name_raw.strip(),
                "returned": int(round(returned)),
                "issued": int(round(issued)) if issued is not None else None,
            }
        )
    return out, as_of


def load_live_bsr() -> dict:
    try:
        raw = fetch_bytes(LIVE_BSR_XLSX)
    except Exception as exc:
        return {
            "status": "not_published",
            "note": f"Could not fetch SOS ballot status workbook: {exc}",
        }
    counties, as_of_cell = parse_bsr_counties(raw)
    if not counties:
        return {
            "status": "parse_failed",
            "source_url": LIVE_BSR_XLSX,
            "note": "SOS bsr-statistics.xlsx downloaded but county rows could not be parsed.",
        }
    return {
        "status": "county_level",
        "source_url": LIVE_BSR_XLSX,
        "as_of": as_of_cell or date.today().isoformat(),
        "counties": counties,
        "note": "County-level mail ballot return counts from CA SOS daily Ballot Status Report (not Assembly-district totals).",
    }


def build_election_snapshot(election_key: str, county_ids: set[int]) -> tuple[dict[int, dict], list[str]]:
    gaps: list[str] = []
    print(f"  {election_key}: loading SOV addist map…", file=sys.stderr)
    addist_map = load_sov_addist_map(election_key, county_ids)
    if not addist_map:
        gaps.append(f"{election_key}: no SOV precinct rows mapped to beachhead ADs")
    print(f"  {election_key}: aggregating VBM…", file=sys.stderr)
    vbm = aggregate_vbm(election_key, addist_map)
    print(f"  {election_key}: aggregating SOV totals…", file=sys.stderr)
    sov = aggregate_sov(election_key, county_ids)
    meta = ELECTIONS[election_key]
    out: dict[int, dict] = {}
    for dist_no in BEACHHEADS.values():
        v = vbm.get(dist_no, {"returned": 0.0, "parties": {}, "srprec_rows": 0})
        s = sov.get(dist_no, {})
        returned = v["returned"]
        reg_sov = s.get("totreg", 0.0)
        if v["srprec_rows"] == 0:
            gaps.append(f"{election_key} AD-{dist_no}: zero VBM precinct rows matched")
        parties = party_rows(dict(v["parties"]), returned)
        out[dist_no] = {
            "election": meta["label"],
            "election_code": meta["election_code"],
            "vbm_returned": int(round(returned)),
            "vbm_pct_of_sov_registration": pct(returned, reg_sov),
            "turnout_pct": pct(s.get("totvote", 0.0), reg_sov),
            "sov_absentee_vote": int(round(s.get("absvote", 0.0))),
            "sov_registration": int(round(reg_sov)),
            "party_returns": parties,
            "source": {
                "vbm": meta["vbm_zip"],
                "sov": "SWDB county SOV by SR precinct (addist)",
            },
        }
    return out, gaps


def main() -> int:
    county_ids: set[int] = set()
    for dist, cids in COUNTIES_BY_AD.items():
        county_ids.update(cids)

    print("Building ABEV baselines from SWDB…", file=sys.stderr)
    g24, gaps24 = build_election_snapshot("g24", county_ids)
    g22, gaps22 = build_election_snapshot("g22", county_ids)
    all_gaps = gaps24 + gaps22

    ror_reg = load_ror_registration()
    live_bsr = load_live_bsr()

    districts = []
    for dist_id, dist_no in BEACHHEADS.items():
        b24 = g24.get(dist_no, {})
        b22 = g22.get(dist_no, {})
        reg_current = ror_reg.get(dist_id)
        pace_note = None
        p24 = b24.get("vbm_pct_of_sov_registration")
        p22 = b22.get("vbm_pct_of_sov_registration")
        if p24 is not None and p22 is not None:
            pace_note = f"2024 final mail returns were {p24}% of SOV registration vs {p22}% in 2022 (SWDB All_VBM)."

        dist_counties = COUNTIES_BY_AD.get(str(dist_no), [])
        county_live = [
            c
            for c in (live_bsr.get("counties") or [])
            if c.get("fips") in dist_counties
        ]
        if live_bsr.get("status") == "county_level" and county_live:
            live_block = {
                "status": "county_level",
                "cycle": "2026",
                "gap_label": "County-level SOS mail ballot returns (not AD totals)",
                "detail": live_bsr.get("note"),
                "source_url": live_bsr.get("source_url"),
                "as_of": live_bsr.get("as_of"),
                "counties": county_live,
                "returned": None,
                "issued": None,
                "pct_of_registration": None,
                "aggregation_note": "Do not sum counties — each row is the full county; AD spans partial counties.",
            }
        else:
            live_block = {
                "status": live_bsr.get("status", "not_published"),
                "cycle": "2026",
                "gap_label": "Live 2026 ballot returns not available at Assembly-district granularity in free public feeds.",
                "detail": live_bsr.get("note"),
                "source_url": live_bsr.get("source_url"),
                "as_of": live_bsr.get("as_of"),
                "counties": county_live or None,
                "returned": None,
                "issued": None,
                "pct_of_registration": None,
            }

        districts.append(
            {
                "id": dist_id,
                "code": f"AD-{dist_no}",
                "registration_current": reg_current,
                "registration_current_source": "CA SOS ROR (demography bundle)" if reg_current else None,
                "live": live_block,
                "baselines": {
                    "primary_compare": "g24",
                    "prior": "g22",
                    "g24": b24,
                    "g22": b22,
                    "pace_note": pace_note,
                },
            }
        )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "schema_version": 1,
        "updated_at": now,
        "built_on": date.today().isoformat(),
        "scope": "Assembly beachhead districts (CRC 2020 lines)",
        "sources": {
            "swdb": {
                "label": "UC Berkeley Statewide Database",
                "home": "https://statewidedatabase.org/",
                "vbm_file_type": "All_VBM (mail ballot voters who returned)",
                "sov_note": "SR precinct SOV includes addist, TOTREG, TOTVOTE, ABSVOTE",
            },
            "registration": {
                "label": "CA SOS Report of Registration",
                "via": str(DEMOGRAPHY.relative_to(ROOT.parent.parent)) if DEMOGRAPHY.is_file() else None,
            },
            "live_sos_bsr": {
                "label": "CA SOS Ballot Status Report (county XLSX)",
                "url": LIVE_BSR_XLSX,
                "assembly_district_limitation": "Workbook is county-level; beachhead rows list intersecting counties only (not apportioned AD totals).",
            },
            "inspiration": {
                "label": "Public statewide ballot-return trackers",
                "url": "",
                "note": "MajorityIQ shows beachhead AD depth, not a statewide clone.",
            },
        },
        "gaps": all_gaps,
        "districts": districts,
    }

    LATEST.mkdir(parents=True, exist_ok=True)
    dated = LATEST / f"abev-by-district-{date.today().isoformat()}.json"
    latest = LATEST / "abev-by-district.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    dated.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(f"Wrote {latest} ({len(districts)} districts, {len(all_gaps)} gap notes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
