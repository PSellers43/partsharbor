#!/usr/bin/env python3
"""Build precinct-level election history GeoJSON for beachhead Assembly districts.

Sources (free / public):
  - UC Berkeley Statewide Database g22 + g24 SOV by SR precinct (Assembly contest)
  - SWDB SR precinct boundaries (g22 v01 shapefile; votes joined by county + SRPREC)
  - CRC 2020 Assembly boundary clip (same as Focus intra map)

Outputs:
  ../latest/ad-{dist}-precincts.geojson  — simplified precinct polygons + vote margins
  ../latest/election-history-index.json   — manifest for the UI loader

Not a voter file; aggregate public results only.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape

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
SCHEMA_VERSION = 1


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


def asm_two_party(row: dict) -> dict:
    dem = num(row.get("ASSDEM01")) + num(row.get("ASSDEM02"))
    rep = num(row.get("ASSREP01")) + num(row.get("ASSREP02"))
    total2 = dem + rep
    if total2 <= 0:
        return {"dem": dem, "rep": rep, "dem_pct": None, "margin_dem": None, "votes_two_party": 0}
    dem_pct = dem / total2 * 100.0
    margin_dem = (dem - rep) / total2 * 100.0
    return {
        "dem": dem,
        "rep": rep,
        "dem_pct": round(dem_pct, 1),
        "margin_dem": round(margin_dem, 1),
        "votes_two_party": int(total2),
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


def build_district(dist: str, ad_poly) -> tuple[dict, list[str]]:
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
    for (cid, srprec), rec in sorted(geometries.items(), key=lambda x: (x[0][0], x[0][1])):
        props = {
            "county_fips": cid,
            "srprec": srprec,
            "precinct_id": f"{cid:03d}-{srprec}",
        }
        has_any = False
        for race_id in RACES:
            stats = race_stats[race_id].get(srprec)
            if stats and stats.get("votes_two_party", 0) > 0:
                has_any = True
                props[race_id] = {
                    "dem_pct": stats["dem_pct"],
                    "margin_dem": stats["margin_dem"],
                    "votes_two_party": stats["votes_two_party"],
                }
            else:
                props[race_id] = None
        if not has_any:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": geom_to_geojson(rec["geom"], PRECINCT_MAX_PTS),
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
            "assembly_boundary": "CRC 2020 (ca-assembly-crc-2020.geojson)",
            "built_at": date.today().isoformat(),
            "races": {k: {"label": v["label"], "election": v["election"]} for k, v in RACES.items()},
        },
        "features": features,
        "outline": geom_to_geojson(ad_poly, 120),
    }
    return fc, gaps


def main() -> int:
    if not ASSEMBLY_GEO.exists():
        print(f"Missing {ASSEMBLY_GEO}", file=sys.stderr)
        return 1

    LATEST.mkdir(parents=True, exist_ok=True)
    ad_polys = load_ad_polygons()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "swdb_g22": "https://statewidedatabase.org/d20/g22.html",
            "swdb_g24": "https://statewidedatabase.org/d20/g24.html",
            "note": "Two-party Assembly margin by SR precinct; not a voter file.",
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
        fc, gaps = build_district(dist, poly)
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
