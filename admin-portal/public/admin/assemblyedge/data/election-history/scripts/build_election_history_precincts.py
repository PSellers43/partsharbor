#!/usr/bin/env python3
"""Build precinct-level election history GeoJSON for beachhead Assembly districts.

Sources (free / public):
  - UC Berkeley Statewide Database g22 + g24 SOV by SR precinct (Assembly contest)
  - SWDB SR precinct boundaries (g22 v01 shapefile; votes joined by county + SRPREC)
  - CRC 2020 Assembly boundary clip (same as Focus intra map)
  - U.S. Census TIGER/Line 2020 cartographic places (incorporated places + CDPs)

Outputs:
  ../latest/ad-{dist}-precincts.geojson  — simplified precinct polygons + vote margins
  ../latest/election-history-index.json   — manifest for the UI loader

Not a voter file; aggregate public results only.
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
MAP_ROOT = ROOT.parent / "map"
ASSEMBLY_GEO = MAP_ROOT / "ca-assembly-crc-2020.geojson"
LATEST = ROOT / "latest"

BEACHHEAD = {"7", "27", "36", "47", "58", "74"}
COUNTY_FIPS = {
    "7": [67, 61],
    "27": [19, 39],
    "36": [25],  # Imperial (CRC AD-36); SOV addist filter — not Kern/LA
    "47": [65],
    "58": [65],
    "74": [59],
}

RACES = {
    "g22_asm": {
        "label": "2022 General · Assembly",
        "election": "2022-11-08",
        "cycle": "g22",
        "sov_template": "https://statewidedatabase.org/pub/data/G22/c{cid:03d}/c{cid:03d}_g22_sov_data_by_g22_srprec.csv",
        "shp_template": "https://statewidedatabase.org/pub/data/G22/c{cid:03d}/srprec_{cid:03d}_g22_v01_shp.zip",
    },
    "g24_asm": {
        "label": "2024 General · Assembly",
        "election": "2024-11-05",
        "cycle": "g24",
        "sov_template": "https://statewidedatabase.org/pub/data/G24/c{cid:03d}/c{cid:03d}_g24_sov_data_by_g24_srprec.csv",
        "shp_template": "https://statewidedatabase.org/pub/data/G24/c{cid:03d}/srprec_{cid:03d}_g24_v01_shp.zip",
    },
}

PRECINCT_MAX_PTS = 32
SCHEMA_VERSION = 2
CENSUS_PLACES_ZIP = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_06_place_500k.zip"
PLACE_MOST_SHARE = 0.5
PLACE_ALSO_MIN_SHARE = 0.10

CA_COUNTY_NAMES = {
    1: "Alameda",
    3: "Alpine",
    5: "Amador",
    7: "Butte",
    9: "Calaveras",
    11: "Colusa",
    13: "Contra Costa",
    15: "Del Norte",
    17: "El Dorado",
    19: "Fresno",
    21: "Glenn",
    23: "Humboldt",
    25: "Imperial",
    27: "Inyo",
    29: "Kern",
    31: "Kings",
    33: "Lake",
    35: "Lassen",
    37: "Los Angeles",
    39: "Madera",
    41: "Marin",
    43: "Mariposa",
    45: "Mendocino",
    47: "Merced",
    49: "Modoc",
    51: "Mono",
    53: "Monterey",
    55: "Napa",
    57: "Nevada",
    59: "Orange",
    61: "Placer",
    63: "Plumas",
    65: "Riverside",
    67: "Sacramento",
    69: "San Benito",
    71: "San Bernardino",
    73: "San Diego",
    75: "San Francisco",
    77: "San Joaquin",
    79: "San Luis Obispo",
    81: "San Mateo",
    83: "Santa Barbara",
    85: "Santa Clara",
    87: "Santa Cruz",
    89: "Shasta",
    91: "Sierra",
    93: "Siskiyou",
    95: "Solano",
    97: "Sonoma",
    99: "Stanislaus",
    101: "Sutter",
    103: "Tehama",
    105: "Trinity",
    107: "Tulare",
    109: "Tuolumne",
    111: "Ventura",
    113: "Yolo",
    115: "Yuba",
}


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "AssemblyEdge-election-history/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def num(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


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


def fix_geom(g):
    if g.is_empty:
        return g
    fixed = g.buffer(0)
    return fixed if not fixed.is_empty else g


def load_ad_polygons() -> dict[str, object]:
    data = json.loads(ASSEMBLY_GEO.read_text(encoding="utf-8"))
    by_dist = {}
    for feat in data.get("features", []):
        p = feat.get("properties") or {}
        if not p.get("beachhead"):
            continue
        dist = str(p.get("dist_no"))
        by_dist[dist] = fix_geom(shape(feat["geometry"]))
    return by_dist


def load_county_sov(url: str) -> list[dict]:
    try:
        text = fetch_bytes(url).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  skip SOV {url}: {exc}", file=sys.stderr)
        return []
    return list(csv.DictReader(io.StringIO(text)))


def race_winner(margin_dem: float | None) -> str | None:
    if margin_dem is None:
        return None
    if margin_dem > 0:
        return "Dem"
    if margin_dem < 0:
        return "Rep"
    return "Tie"


def asm_two_party(row: dict) -> dict:
    dem = num(row.get("ASSDEM01")) + num(row.get("ASSDEM02"))
    rep = num(row.get("ASSREP01")) + num(row.get("ASSREP02"))
    total2 = dem + rep
    if total2 <= 0:
        return {
            "dem": dem,
            "rep": rep,
            "dem_pct": None,
            "margin_dem": None,
            "votes_two_party": 0,
            "winner": None,
        }
    dem_pct = dem / total2 * 100.0
    margin_dem = (dem - rep) / total2 * 100.0
    margin_r = round(margin_dem, 1)
    return {
        "dem": dem,
        "rep": rep,
        "dem_pct": round(dem_pct, 1),
        "margin_dem": margin_r,
        "votes_two_party": int(total2),
        "winner": race_winner(margin_r),
    }


def area_sq_mi(geom) -> float:
    """Planar approximation in sq mi (adequate for small precinct polygons)."""
    if geom.is_empty:
        return 0.0
    centroid = geom.centroid
    lat = centroid.y
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    m_per_deg_lat = 110540.0

    def _scale(x, y, z=None):
        return (x * m_per_deg_lon, y * m_per_deg_lat)

    projected = transform(_scale, geom)
    sq_m = projected.area
    return round(sq_m / (1609.34**2), 3)


def geom_bbox(geom) -> list[float]:
    minx, miny, maxx, maxy = geom.bounds
    return [round(minx, 5), round(miny, 5), round(maxx, 5), round(maxy, 5)]


def load_places() -> list[dict]:
    import shapefile  # pyshp

    raw = fetch_bytes(CENSUS_PLACES_ZIP)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    base = next(n for n in zf.namelist() if n.endswith(".shp")).replace(".shp", "")
    tmp = ROOT / "scripts" / "_tmp_places_eh"
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
        name = str(rec[name_i]).strip()
        geoid = str(rec[geoid_i]).strip()
        lsad = str(rec[lsad_i]).strip()
        kind = "city" if lsad in ("25", "00") else "cdp"
        geom = fix_geom(shape(sr.shape.__geo_interface__))
        if geom.is_empty:
            continue
        out.append({"name": name, "geoid": geoid, "kind": kind, "geom": geom})
    return out


def places_for_ad(all_places: list[dict], ad_poly) -> tuple[list[dict], STRtree]:
    subset = []
    for pl in all_places:
        if ad_poly.intersects(pl["geom"]):
            subset.append(pl)
    tree = STRtree([p["geom"] for p in subset]) if subset else None
    return subset, tree


def place_overlap_props(geom, precinct_area: float, places: list[dict], tree: STRtree | None, county_fips: int) -> dict:
    county_name = CA_COUNTY_NAMES.get(county_fips, f"County {county_fips:03d}")
    uninc_label = f"Unincorporated {county_name} County"
    if precinct_area <= 0 or tree is None or not places:
        return {
            "county_name": county_name,
            "area_sq_mi": area_sq_mi(geom),
            "place_primary": uninc_label,
            "place_primary_share": None,
            "place_also": [],
            "places": [],
            "place_matched": False,
        }

    overlaps: list[tuple[float, dict]] = []
    for idx in tree.query(geom):
        pl = places[int(idx)]
        inter = fix_geom(geom.intersection(pl["geom"]))
        if inter.is_empty or inter.area <= 0:
            continue
        share = inter.area / precinct_area
        if share < 0.001:
            continue
        overlaps.append((share, pl))

    overlaps.sort(key=lambda x: -x[0])
    place_rows = [
        {
            "name": pl["name"],
            "geoid": pl["geoid"],
            "kind": pl["kind"],
            "pct": round(share * 100, 1),
        }
        for share, pl in overlaps
    ]
    also = [pl["name"] for share, pl in overlaps[1:] if share >= PLACE_ALSO_MIN_SHARE]

    top_share = overlaps[0][0] if overlaps else 0.0
    if top_share >= PLACE_MOST_SHARE:
        primary = overlaps[0][1]["name"]
        matched = True
    else:
        primary = uninc_label
        matched = False

    return {
        "county_name": county_name,
        "area_sq_mi": area_sq_mi(geom),
        "place_primary": primary,
        "place_primary_share": round(top_share * 100, 1) if overlaps else None,
        "place_also": also[:6],
        "places": place_rows[:8],
        "place_matched": matched,
    }


def sov_for_ad(rows: list[dict], ad_dist: str) -> dict[str, dict]:
    target = int(ad_dist)
    out = {}
    for row in rows:
        if int(num(row.get("addist"))) != target:
            continue
        srprec = (row.get("srprec") or "").strip()
        if not srprec:
            continue
        out[srprec] = asm_two_party(row)
    return out


def load_srprec_shapes(cid: int, cycle: str) -> list[dict]:
    import shapefile  # pyshp

    race = RACES["g22_asm" if cycle == "g22" else "g24_asm"]
    url = race["shp_template"].format(cid=cid)
    raw = fetch_bytes(url)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    base = next(n for n in zf.namelist() if n.endswith(".shp")).replace(".shp", "")
    tmp = ROOT / "scripts" / "_tmp_srprec"
    tmp.mkdir(parents=True, exist_ok=True)
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        name = base + ext
        if name in zf.namelist():
            (tmp / (f"{cid}_{cycle}" + ext)).write_bytes(zf.read(name))
    shp_path = tmp / f"{cid}_{cycle}.shp"
    reader = shapefile.Reader(str(shp_path))
    field_names = [f[0] for f in reader.fields[1:]]
    srprec_i = None
    for cand in ("SRPREC", "srprec", "SR_PREC"):
        if cand in field_names:
            srprec_i = field_names.index(cand)
            break
    out = []
    for sr in reader.shapeRecords():
        rec = sr.record
        srprec = str(rec[srprec_i]).strip() if srprec_i is not None else ""
        geom = fix_geom(shape(sr.shape.__geo_interface__))
        if geom.is_empty:
            continue
        out.append({"srprec": srprec, "geom": geom})
    return out


def build_district(
    dist: str, ad_poly, places: list[dict], place_tree: STRtree | None
) -> tuple[dict, list[str], dict]:
    gaps: list[str] = []
    race_stats: dict[str, dict[str, dict]] = {k: {} for k in RACES}
    geometries: dict[tuple[int, str], dict] = {}

    for cid in COUNTY_FIPS.get(dist, []):
        print(f"  county {cid:03d} …")
        for race_id, meta in RACES.items():
            sov_url = meta["sov_template"].format(cid=cid)
            rows = load_county_sov(sov_url)
            if not rows:
                gaps.append(f"AD-{dist}: missing SOV for {race_id} in county {cid:03d}")
                continue
            race_stats[race_id].update(sov_for_ad(rows, dist))

        # Prefer g22 boundaries (stable, smaller); fall back to g24 if g22 shapes fail
        shapes = []
        for cycle in ("g22", "g24"):
            try:
                shapes = load_srprec_shapes(cid, cycle)
                if shapes:
                    break
            except Exception as exc:
                print(f"    shape load {cycle} failed: {exc}", file=sys.stderr)
        if not shapes:
            gaps.append(f"AD-{dist}: no SR precinct shapes for county {cid:03d}")
            continue

        for sh in shapes:
            key = (cid, sh["srprec"])
            if key in geometries:
                continue
            geom = sh["geom"]
            if not ad_poly.intersects(geom):
                continue
            inter = fix_geom(ad_poly.intersection(geom))
            if inter.is_empty or inter.area <= 0:
                continue
            geometries[key] = {"county_fips": cid, "srprec": sh["srprec"], "geom": inter}

    features = []
    place_matched_count = 0
    for (cid, srprec), rec in sorted(geometries.items(), key=lambda x: (x[0][0], x[0][1])):
        geom = rec["geom"]
        precinct_area = geom.area
        props = {
            "county_fips": cid,
            "srprec": srprec,
            "precinct_id": f"{cid:03d}-{srprec}",
        }
        props.update(place_overlap_props(geom, precinct_area, places, place_tree, cid))
        matched_place = props.pop("place_matched", False)
        props["bbox"] = geom_bbox(geom)
        has_any = False
        for race_id in RACES:
            stats = race_stats[race_id].get(srprec)
            if stats and stats.get("votes_two_party", 0) > 0:
                has_any = True
                props[race_id] = {
                    "dem_pct": stats["dem_pct"],
                    "margin_dem": stats["margin_dem"],
                    "votes_two_party": stats["votes_two_party"],
                    "winner": stats.get("winner"),
                }
            else:
                props[race_id] = None
        if not has_any:
            continue
        if matched_place:
            place_matched_count += 1
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": geom_to_geojson(geom, PRECINCT_MAX_PTS),
            }
        )

    if not features:
        gaps.append(f"AD-{dist}: no precinct features with Assembly vote totals")

    fc = {
        "type": "FeatureCollection",
        "district_id": f"ad-{dist}",
        "district_code": f"AD-{dist}",
        "schema_version": SCHEMA_VERSION,
        "source": {
            "boundaries": "UC Berkeley Statewide Database SR precinct shapefiles (g22/g24 v01)",
            "results": "SWDB SOV by SR precinct — Assembly contest (ASSDEM* vs ASSREP*)",
            "places": "U.S. Census Bureau TIGER/Line 2020 cartographic places (cb_2020_06_place_500k)",
            "assembly_boundary": "CRC 2020 (ca-assembly-crc-2020.geojson)",
            "built_at": date.today().isoformat(),
            "races": {k: {"label": v["label"], "election": v["election"]} for k, v in RACES.items()},
        },
        "features": features,
        "outline": geom_to_geojson(ad_poly, 120),
    }
    place_stats = {
        "precinct_count": len(features),
        "place_primary_matched": place_matched_count,
        "place_primary_matched_pct": round(
            100.0 * place_matched_count / len(features), 1
        )
        if features
        else 0.0,
    }
    return fc, gaps, place_stats


def main() -> int:
    if not ASSEMBLY_GEO.exists():
        print(f"Missing {ASSEMBLY_GEO}", file=sys.stderr)
        return 1

    LATEST.mkdir(parents=True, exist_ok=True)
    ad_polys = load_ad_polygons()
    print("Loading Census places (CA) …")
    all_places = load_places()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "swdb_g22": "https://statewidedatabase.org/d20/g22.html",
            "swdb_g24": "https://statewidedatabase.org/d20/g24.html",
            "census_places": "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_06_place_500k.zip",
            "note": "Two-party Assembly margin by SR precinct; place labels from Census TIGER overlaps. Not a voter file.",
        },
        "districts": [],
        "gaps": [],
    }

    for dist in sorted(BEACHHEAD, key=int):
        poly = ad_polys.get(dist)
        if poly is None:
            manifest["gaps"].append(f"AD-{dist}: missing beachhead boundary polygon")
            continue
        print(f"Building AD-{dist} precinct history …")
        ad_places, place_tree = places_for_ad(all_places, poly)
        print(f"  {len(ad_places)} Census places intersect AD-{dist}")
        fc, gaps, place_stats = build_district(dist, poly, ad_places, place_tree)
        manifest["gaps"].extend(gaps)
        out_name = f"ad-{dist}-precincts.geojson"
        out_path = LATEST / out_name
        out_path.write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
        size_kb = out_path.stat().st_size // 1024
        print(f"  Wrote {out_path} ({size_kb} KB, {len(fc['features'])} precincts)")

        races_present = []
        for rid in RACES:
            if any(
                (f.get("properties") or {}).get(rid) and (f["properties"][rid] or {}).get("votes_two_party")
                for f in fc["features"]
            ):
                races_present.append(rid)

        manifest["districts"].append(
            {
                "id": f"ad-{dist}",
                "code": f"AD-{dist}",
                "file": out_name,
                "precinct_count": len(fc["features"]),
                "place_primary_matched": place_stats["place_primary_matched"],
                "place_primary_matched_pct": place_stats["place_primary_matched_pct"],
                "races": races_present,
                "gaps": [g for g in gaps if g.startswith(f"AD-{dist}")],
            }
        )

    dated = LATEST / f"election-history-index-{date.today().isoformat()}.json"
    index_path = LATEST / "election-history-index.json"
    payload = json.dumps(manifest, indent=2)
    index_path.write_text(payload + "\n", encoding="utf-8")
    dated.write_text(payload + "\n", encoding="utf-8")
    print(f"Wrote {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
