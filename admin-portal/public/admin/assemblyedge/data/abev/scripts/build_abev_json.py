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
    "27": [19, 39],
    "36": [29, 37],
    "47": [65],
    "58": [65],
    "74": [59],
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

LIVE_VBM_PDF_CANDIDATES = [
    "https://elections.cdn.sos.ca.gov/statewide-elections/2026-general/vbm-statistics.pdf",
    "https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/vbm-statistics.pdf",
]

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


def probe_live_sos_vbm() -> dict:
    """Best-effort HEAD on SOS VoteCal VBM PDFs (county-level; not AD)."""
    for url in LIVE_VBM_PDF_CANDIDATES:
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "MajorityIQ-abev-build/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    return {
                        "status": "county_pdf_only",
                        "source_url": url,
                        "note": "SOS VoteCal VBM PDF is county-level; Assembly district live returns not in this feed.",
                    }
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
        except Exception:
            continue
    return {
        "status": "not_published",
        "note": "No 2026 SOS VoteCal VBM statistics PDF found at expected URLs.",
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
    live_probe = probe_live_sos_vbm()

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

        districts.append(
            {
                "id": dist_id,
                "code": f"AD-{dist_no}",
                "registration_current": reg_current,
                "registration_current_source": "CA SOS ROR (demography bundle)" if reg_current else None,
                "live": {
                    "status": live_probe["status"],
                    "cycle": "2026",
                    "gap_label": "Live 2026 ballot returns not available at Assembly-district granularity in free public feeds.",
                    "detail": live_probe.get("note"),
                    "sos_probe_url": live_probe.get("source_url"),
                    "returned": None,
                    "accepted": None,
                    "issued": None,
                    "as_of": None,
                    "pct_of_registration": None,
                },
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
            "live_sos_vbm": {
                "label": "CA SOS VoteCal VBM statistics (county PDF)",
                "pattern": "https://elections.cdn.sos.ca.gov/statewide-elections/{cycle}/vbm-statistics.pdf",
                "assembly_district_limitation": "PDF is county-level; AD aggregation requires county feeds or SWDB-style precinct joins.",
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
