#!/usr/bin/env python3
"""Build intra-district (city / CDP) focus layers for beachhead Assembly districts.

Sources (free / public):
  - CRC 2020 Assembly boundaries (same as statewide Focus map)
  - U.S. Census Bureau 2020 cartographic places (cb_2020_06_place_500k)
  - UC Berkeley Statewide Database 2022 General (g22) SOV by SR precinct + SRPREC→city

Focus score (0–100, illustrative ops proxy — not field intelligence):
  70% competitiveness from 2022 Assembly contest two-party margin in each place
  30% turnout (ballots cast / registration) in overlapping SR precincts

Outputs one GeoJSON per beachhead under ../intra/ad-{dist}.geojson
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from shapely.geometry import mapping, shape
ROOT = Path(__file__).resolve().parents[1]
ASSEMBLY_GEO = ROOT / "ca-assembly-crc-2020.geojson"
INTRA_DIR = ROOT / "intra"
CENSUS_PLACES_ZIP = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_06_place_500k.zip"
SWDB_CITY_CONV = "https://statewidedatabase.org/pub/data/G22/state/state_g22_srprec_to_city.csv"
SWDB_SOV_TEMPLATE = "https://statewidedatabase.org/pub/data/G22/c{cid:03d}/c{cid:03d}_g22_sov_data_by_g22_srprec.csv"

BEACHHEAD = {"7", "27", "36", "47", "58", "74"}
# Counties likely needed (script also skips missing CSVs gracefully)
COUNTY_FIPS = {
    "7": [67, 61],
    "27": [19, 39],
    "36": [25, 65],  # Imperial + Riverside (CRC AD-36 Coachella / Imperial — not Kern/LA)
    "47": [65],
    "58": [65],
    "74": [59],
}
PLACE_MAX_PTS = 48


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "AssemblyEdge-build/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def simplify_ring(ring: list, max_pts: int) -> list:
    if not ring:
        return ring
    closed = ring[0] == ring[-1]
    core = ring[:-1] if closed and len(ring) > 1 else list(ring)
    if len(core) <= max_pts:
        out = [[round(x, 5), round(y, 5)] for x, y in core]
    else:
        step = max(1, len(core) // max_pts)
        out = [[round(core[i][0], 5), round(core[i][1], 5)] for i in range(0, len(core), step)]
    if closed and out and out[0] != out[-1]:
        out.append(out[0][:])
    return out


def geom_to_geojson(geom, max_pts: int) -> dict:
    g = mapping(geom)
    t = g["type"]
    if t == "Polygon":
        g["coordinates"] = [simplify_ring(r, max_pts) for r in g["coordinates"]]
    elif t == "MultiPolygon":
        g["coordinates"] = [[simplify_ring(r, max_pts) for r in poly] for poly in g["coordinates"]]
    return g


def load_places():
    import shapefile  # pyshp

    raw = fetch_bytes(CENSUS_PLACES_ZIP)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    base = next(n for n in zf.namelist() if n.endswith(".shp")).replace(".shp", "")
    tmp = ROOT / "scripts" / "_tmp_places"
    tmp.mkdir(parents=True, exist_ok=True)
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        name = base + ext
        if name in zf.namelist():
            (tmp / Path(name).name).write_bytes(zf.read(name))
    shp_path = tmp / (Path(base).name + ".shp")
    reader = shapefile.Reader(str(shp_path))
    field_names = [f[0] for f in reader.fields[1:]]
    name_i = field_names.index("NAME")
    geoid_i = field_names.index("GEOID")
    lsad_i = field_names.index("LSAD")
    out = []
    for sr in reader.shapeRecords():
        rec = sr.record
        name = rec[name_i]
        geoid = rec[geoid_i]
        lsad = rec[lsad_i]
        kind = "city" if str(lsad) in ("25", "00") else "place"
        geom = fix_geom(shape(sr.shape.__geo_interface__))
        if geom.is_empty:
            continue
        out.append({"name": name, "geoid": geoid, "kind": kind, "geom": geom})
    return out


def fix_geom(g):
    if g.is_empty:
        return g
    fixed = g.buffer(0)
    return fixed if not fixed.is_empty else g


def load_ad_polygons():
    data = json.loads(ASSEMBLY_GEO.read_text(encoding="utf-8"))
    by_dist = {}
    for feat in data.get("features", []):
        p = feat.get("properties") or {}
        if not p.get("beachhead"):
            continue
        dist = str(p.get("dist_no"))
        by_dist[dist] = fix_geom(shape(feat["geometry"]))
    return by_dist


def load_city_conv():
    text = fetch_bytes(SWDB_CITY_CONV).decode("utf-8", errors="replace")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        rows.append(row)
    return rows


def load_county_sov(cid: int) -> list[dict]:
    url = SWDB_SOV_TEMPLATE.format(cid=cid)
    try:
        text = fetch_bytes(url).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  skip county {cid:03d} SOV: {exc}", file=sys.stderr)
        return []
    return list(csv.DictReader(io.StringIO(text)))


def norm_place(name: str) -> str:
    return " ".join((name or "").upper().split())


def num(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute_focus(dem: float, rep: float, reg: float, vote: float) -> dict:
    total2 = dem + rep
    if total2 <= 0:
        comp = 0.0
        dem_pct = None
    else:
        dem_pct = dem / total2 * 100.0
        margin = abs(dem - rep) / total2
        comp = (1.0 - margin) * 100.0
    turnout = min(100.0, (vote / reg * 100.0)) if reg > 0 else 0.0
    score = round(0.7 * comp + 0.3 * turnout)
    score = max(0, min(100, score))
    return {"score": score, "dem_pct": round(dem_pct, 1) if dem_pct is not None else None, "turnout_pct": round(turnout, 1)}


def precinct_stats_for_ad(county_rows: list[dict], ad_dist: str) -> dict[str, dict]:
    """SRPREC -> vote stats for precincts in this AD."""
    out = {}
    target = int(ad_dist)
    for row in county_rows:
        if int(num(row.get("addist"))) != target:
            continue
        srprec = (row.get("srprec") or "").strip()
        dem = num(row.get("ASSDEM01"))
        rep = num(row.get("ASSREP01")) + num(row.get("ASSREP02"))
        reg = num(row.get("TOTREG"))
        vote = num(row.get("TOTVOTE"))
        out[srprec] = {"dem": dem, "rep": rep, "reg": reg, "vote": vote}
    return out


def city_vote_totals(city_conv, county_fips: int, precinct_stats: dict[str, dict]) -> dict[str, dict]:
    """Aggregate SR precinct votes to city names using SWDB SRPREC→city weights."""
    acc = defaultdict(lambda: {"dem": 0.0, "rep": 0.0, "reg": 0.0, "vote": 0.0, "weight": 0.0})
    fips_key = f"06{county_fips:03d}"
    for row in city_conv:
        if (row.get("FIPS") or "").strip() != fips_key:
            continue
        srprec = (row.get("SRPREC") or row.get("srprec") or "").strip()
        if srprec not in precinct_stats:
            continue
        city = norm_place((row.get("CITY") or row.get("city") or "Unknown").strip())
        n_in = num(row.get("N_IN_CITY") or row.get("n_in_city"))
        n_total = num(row.get("N") or row.get("n"))
        if n_total <= 0:
            continue
        w = n_in / n_total
        ps = precinct_stats[srprec]
        acc[city]["dem"] += ps["dem"] * w
        acc[city]["rep"] += ps["rep"] * w
        acc[city]["reg"] += ps["reg"] * w
        acc[city]["vote"] += ps["vote"] * w
        acc[city]["weight"] += w
    return acc


def build_district(dist: str, ad_poly, places, city_conv) -> dict:
    ad_int = int(dist)
    clipped = []
    ad_poly = fix_geom(ad_poly)
    for pl in places:
        pg = fix_geom(pl["geom"])
        if not ad_poly.intersects(pg):
            continue
        inter = fix_geom(ad_poly.intersection(pg))
        if inter.is_empty or inter.area <= 0:
            continue
        if not inter.intersects(ad_poly.representative_point()):
            # keep places with meaningful overlap
            if inter.area / pg.area < 0.05:
                continue
        clipped.append({**pl, "geom": inter})

    # Election aggregates
    city_votes: dict[str, dict] = defaultdict(lambda: {"dem": 0.0, "rep": 0.0, "reg": 0.0, "vote": 0.0})
    for cid in COUNTY_FIPS.get(dist, []):
        sov = load_county_sov(cid)
        if not sov:
            continue
        pstats = precinct_stats_for_ad(sov, dist)
        cv = city_vote_totals(city_conv, cid, pstats)
        for city, vals in cv.items():
            for k in ("dem", "rep", "reg", "vote"):
                city_votes[city][k] += vals[k]

    features = []
    for pl in sorted(clipped, key=lambda x: (-x["geom"].area, x["name"])):
        cv = city_votes.get(norm_place(pl["name"]), {"dem": 0, "rep": 0, "reg": 0, "vote": 0})
        metrics = compute_focus(cv["dem"], cv["rep"], cv["reg"], cv["vote"])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": pl["name"],
                    "geoid": pl["geoid"],
                    "kind": pl["kind"],
                    "focus_score": metrics["score"],
                    "dem_pct_2022_asm": metrics["dem_pct"],
                    "turnout_pct_2022": metrics["turnout_pct"],
                    "has_election_data": cv["dem"] + cv["rep"] > 0,
                },
                "geometry": geom_to_geojson(pl["geom"], PLACE_MAX_PTS),
            }
        )

    outline = geom_to_geojson(ad_poly, 120)
    return {
        "type": "FeatureCollection",
        "district_id": f"ad-{dist}",
        "district_code": f"AD-{dist}",
        "source": {
            "places": "U.S. Census Bureau cartographic places (cb_2020_06_place_500k)",
            "election": "UC Berkeley Statewide Database 2022 General (g22) SOV by SR precinct",
            "city_join": SWDB_CITY_CONV,
            "assembly_boundary": str(ASSEMBLY_GEO.name),
            "built_at": date.today().isoformat(),
            "score_formula": (
                "Illustrative focus (0–100) = 70% competitiveness from 2022 Assembly two-party margin "
                "+ 30% turnout (TOTVOTE/TOTREG) in overlapping SR precincts, aggregated to place via "
                "SWDB SRPREC→city weights. Not a field targeting model."
            ),
        },
        "features": features,
        "outline": outline,
    }


def main() -> int:
    if not ASSEMBLY_GEO.exists():
        print(f"Missing {ASSEMBLY_GEO}; run build_focus_map_geojson.py first.", file=sys.stderr)
        return 1

    INTRA_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading Census places …")
    places = load_places()
    print(f"  {len(places)} places in CA")

    print("Loading beachhead AD polygons …")
    ad_polys = load_ad_polygons()
    missing = BEACHHEAD - set(ad_polys)
    if missing:
        print(f"Warning: missing beachhead polygons: {missing}", file=sys.stderr)

    print("Loading SWDB SRPREC→city conversion …")
    city_conv = load_city_conv()

    for dist in sorted(BEACHHEAD, key=int):
        poly = ad_polys.get(dist)
        if poly is None:
            continue
        print(f"Building AD-{dist} …")
        fc = build_district(dist, poly, places, city_conv)
        out_path = INTRA_DIR / f"ad-{dist}.geojson"
        out_path.write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
        print(f"  Wrote {out_path} ({out_path.stat().st_size} bytes, {len(fc['features'])} places)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
