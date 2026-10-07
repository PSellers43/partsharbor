/* MajorityIQ — focus / opportunity score + map helpers */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.focusMap = AE.focusMap || {};
  AE.mapGeo = null;
  AE.mapGeoLoadError = null;

  const DEFAULT_BOUNDS = { minLon: -124.5, maxLon: -114, minLat: 32.4, maxLat: 42.2 };

  /**
   * Focus / opportunity score (0–100, prototype):
   *   40% Threat Index (demo desk signal, normalized)
   *   35% Money pressure (live CAL-ACCESS spend when matched, else TI proxy)
   *   25% Polling gap severity (no recent public horse-race poll → higher)
   * Documented on Focus map page + Methodology card.
   */
  AE.focusMap.computeScore = function (districtId) {
    const d = AE.districts.find((x) => x.id === districtId);
    if (!d) return { score: 0, parts: {} };

    const tiPart = Math.min(100, Math.max(0, d.threatIndex)) / 100;

    let moneyPart = tiPart * 0.85;
    const liveDist = AE.liveMoney && AE.liveMoney.districts && AE.liveMoney.districts[districtId];
    if (liveDist && liveDist.live) {
      const spend = (liveDist.candidates || []).concat(liveDist.ie || []).reduce((sum, r) => {
        const s = typeof r.spend === "number" ? r.spend : 0;
        return sum + s;
      }, 0);
      const cap = 800000;
      moneyPart = Math.min(1, spend / cap);
    }

    const gapPart = AE.polling && AE.polling.gapSeverity ? AE.polling.gapSeverity(districtId) : 1;

    const score = Math.round(100 * (0.4 * tiPart + 0.35 * moneyPart + 0.25 * gapPart));
    return {
      score: Math.min(100, Math.max(0, score)),
      parts: {
        threatIndex: d.threatIndex,
        tiPart: Math.round(tiPart * 100),
        moneyPart: Math.round(moneyPart * 100),
        gapPart: Math.round(gapPart * 100),
      },
    };
  };

  AE.focusMap.scoreBand = function (score) {
    if (score >= 70) return { label: "High focus", class: "focus-high" };
    if (score >= 50) return { label: "Elevated", class: "focus-mid" };
    return { label: "Watch", class: "focus-low" };
  };

  AE.focusMap.loadGeo = function () {
    AE.mapGeo = null;
    AE.mapGeoLoadError = null;
    return fetch("data/map/ca-assembly-crc-2020.geojson", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.mapGeo = json;
        AE.mapGeo._bounds = AE.focusMap.computeBounds(json);
        AE.mapGeoLoadError = null;
      })
      .catch((err) => {
        AE.mapGeo = null;
        AE.mapGeoLoadError = String(err && err.message ? err.message : err);
      });
  };

  AE.focusMap.computeBounds = function (geo) {
    let minLon = Infinity;
    let maxLon = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;

    function walkCoords(coords) {
      if (typeof coords[0] === "number") {
        const lon = coords[0];
        const lat = coords[1];
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        return;
      }
      coords.forEach(walkCoords);
    }

    (geo.features || []).forEach((f) => {
      if (f.geometry && f.geometry.coordinates) walkCoords(f.geometry.coordinates);
    });

    if (!Number.isFinite(minLon)) return DEFAULT_BOUNDS;
    const padLon = (maxLon - minLon) * 0.02 || 0.1;
    const padLat = (maxLat - minLat) * 0.02 || 0.1;
    return {
      minLon: minLon - padLon,
      maxLon: maxLon + padLon,
      minLat: minLat - padLat,
      maxLat: maxLat + padLat,
    };
  };

  AE.focusMap.bounds = function () {
    if (AE.mapGeo && AE.mapGeo._bounds) return AE.mapGeo._bounds;
    return DEFAULT_BOUNDS;
  };

  AE.focusMap.attributionHtml = function () {
    const src = AE.mapGeo && AE.mapGeo.source;
    if (!src) {
      return "District boundaries: California Citizens Redistricting Commission (2020) via <a href=\"https://wedrawthelines.ca.gov/final-maps/\" target=\"_blank\" rel=\"noopener noreferrer\">wedrawthelines.ca.gov</a> / <a href=\"https://data.ca.gov/dataset/california-state-assembly-districts-map-2020\" target=\"_blank\" rel=\"noopener noreferrer\">data.ca.gov</a>.";
    }
    const fetched = src.fetched_at ? ` · Built ${src.fetched_at}` : "";
    return (
      `District boundaries: CRC 2020 Assembly final maps (${src.authority || "CRC"})` +
      fetched +
      `. Sources: <a href="${src.wedrawthelines || "https://wedrawthelines.ca.gov/final-maps/"}" target="_blank" rel="noopener noreferrer">wedrawthelines.ca.gov</a>, ` +
      `<a href="${src.dataset || "https://data.ca.gov/dataset/california-state-assembly-districts-map-2020"}" target="_blank" rel="noopener noreferrer">data.ca.gov</a>` +
      (src.download_kml
        ? ` (<a href="${src.download_kml}" target="_blank" rel="noopener noreferrer">official KML</a>).`
        : ".")
    );
  };

  /** Lon/lat → SVG using data-driven bounds. */
  AE.focusMap.project = function (lon, lat, width, height, bounds) {
    const b = bounds || AE.focusMap.bounds();
    const x = ((lon - b.minLon) / (b.maxLon - b.minLon)) * width;
    const y = height - ((lat - b.minLat) / (b.maxLat - b.minLat)) * height;
    return [x, y];
  };

  AE.focusMap.ringToPath = function (ring, width, height, bounds) {
    return (
      ring
        .map((pt, i) => {
          const [x, y] = AE.focusMap.project(pt[0], pt[1], width, height, bounds);
          return (i === 0 ? "M" : "L") + x.toFixed(2) + " " + y.toFixed(2);
        })
        .join(" ") + " Z"
    );
  };

  function pathsForFeature(f, width, height, bounds) {
    const paths = [];
    const geom = f.geometry;
    if (geom.type === "Polygon") {
      geom.coordinates.forEach((ring) => paths.push(AE.focusMap.ringToPath(ring, width, height, bounds)));
    } else if (geom.type === "MultiPolygon") {
      geom.coordinates.forEach((poly) => poly.forEach((ring) => paths.push(AE.focusMap.ringToPath(ring, width, height, bounds))));
    }
    return paths.join(" ");
  }

  AE.focusMap.featurePaths = function (width, height) {
    if (!AE.mapGeo || !AE.mapGeo.features) return { context: [], beachhead: [] };
    const bounds = AE.focusMap.bounds();
    const context = [];
    const beachhead = [];

    AE.mapGeo.features.forEach((f) => {
      const p = f.properties || {};
      const distNo = p.dist_no;
      const isBeach = !!p.beachhead;
      const d = pathsForFeature(f, width, height, bounds);
      if (!d) return;

      if (isBeach) {
        const id = p.id || "ad-" + distNo;
        const { score } = AE.focusMap.computeScore(id);
        const band = AE.focusMap.scoreBand(score);
        beachhead.push({
          id,
          code: p.code || "AD-" + distNo,
          distNo,
          d,
          score,
          band,
        });
      } else {
        context.push({
          distNo,
          code: p.code || "AD-" + distNo,
          d,
        });
      }
    });

    return { context, beachhead };
  };
})();
