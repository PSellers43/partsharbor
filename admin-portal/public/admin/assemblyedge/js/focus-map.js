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

  AE.focusMap.computeBounds = function (geo, options) {
    options = options || {};
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
    const outline = geo.outline || options.outline;
    if (outline && outline.coordinates) walkCoords(outline.coordinates);

    if (!Number.isFinite(minLon)) return DEFAULT_BOUNDS;
    const padRatio = options.padRatio != null ? options.padRatio : 0.02;
    const padLon = (maxLon - minLon) * padRatio || 0.1;
    const padLat = (maxLat - minLat) * padRatio || 0.1;
    return {
      minLon: minLon - padLon,
      maxLon: maxLon + padLon,
      minLat: minLat - padLat,
      maxLat: maxLat + padLat,
    };
  };

  AE.focusMap.mergeBounds = function (boxes) {
    if (!boxes || !boxes.length) return DEFAULT_BOUNDS;
    return boxes.reduce(
      (acc, b) => ({
        minLon: Math.min(acc.minLon, b.minLon),
        maxLon: Math.max(acc.maxLon, b.maxLon),
        minLat: Math.min(acc.minLat, b.minLat),
        maxLat: Math.max(acc.maxLat, b.maxLat),
      }),
      {
        minLon: Infinity,
        maxLon: -Infinity,
        minLat: Infinity,
        maxLat: -Infinity,
      }
    );
  };

  /** Drill maps: padded geographic bounds + cos(lat); no letterboxing (viewBox aspect matches shape). */
  AE.focusMap.prepareDrillBounds = function (bounds, padRatio) {
    const b = bounds || DEFAULT_BOUNDS;
    const refLat = (b.minLat + b.maxLat) / 2;
    const cosLat = Math.cos((refLat * Math.PI) / 180);
    const lonSpan = b.maxLon - b.minLon || 0.02;
    const latSpan = b.maxLat - b.minLat || 0.02;
    const pad = padRatio != null ? padRatio : 0.04;
    const padLon = lonSpan * pad;
    const padLat = latSpan * pad;
    return {
      minLon: b.minLon - padLon,
      maxLon: b.maxLon + padLon,
      minLat: b.minLat - padLat,
      maxLat: b.maxLat + padLat,
      cosLat,
    };
  };

  AE.focusMap.drillProjectedSpans = function (bounds) {
    const b = bounds || DEFAULT_BOUNDS;
    const cosLat = AE.focusMap.drillCosLat(b);
    return {
      spanX: Math.max((b.maxLon - b.minLon) * cosLat, 1e-6),
      spanY: Math.max(b.maxLat - b.minLat, 1e-6),
    };
  };

  /**
   * ViewBox pixel size from projected shape aspect (width fixed at baseW unless height clamps).
   * opts: { minH, maxH, minW, maxW, baseW }
   */
  AE.focusMap.drillViewBoxSize = function (bounds, opts) {
    opts = opts || {};
    const baseW = opts.baseW != null ? opts.baseW : 400;
    const minH = opts.minH != null ? opts.minH : 168;
    const maxH = opts.maxH != null ? opts.maxH : 520;
    const minW = opts.minW != null ? opts.minW : 280;
    const maxW = opts.maxW != null ? opts.maxW : 640;
    const { spanX, spanY } = AE.focusMap.drillProjectedSpans(bounds);
    let w = baseW;
    let h = baseW * (spanY / spanX);
    if (h > maxH) {
      h = maxH;
      w = h * (spanX / spanY);
    } else if (h < minH) {
      h = minH;
      w = h * (spanX / spanY);
    }
    w = Math.min(maxW, Math.max(minW, w));
    h = Math.min(maxH, Math.max(minH, h));
    return { w: Math.round(w * 100) / 100, h: Math.round(h * 100) / 100 };
  };

  /** @deprecated alias — use prepareDrillBounds; width/height ignored (aspect comes from viewBox). */
  AE.focusMap.fitDrillBounds = function (bounds, width, height, padRatio) {
    return AE.focusMap.prepareDrillBounds(bounds, padRatio);
  };

  AE.focusMap.drillCosLat = function (bounds) {
    if (bounds && bounds.cosLat != null) return bounds.cosLat;
    const refLat = bounds ? (bounds.minLat + bounds.maxLat) / 2 : 36;
    return Math.cos((refLat * Math.PI) / 180);
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

  /** Focus drill / election history maps (cos lat + shared bounds). */
  AE.focusMap.projectDrill = function (lon, lat, width, height, bounds) {
    const b = bounds || DEFAULT_BOUNDS;
    const cosLat = AE.focusMap.drillCosLat(b);
    const minX = b.minLon * cosLat;
    const maxX = b.maxLon * cosLat;
    const x = ((lon * cosLat - minX) / (maxX - minX)) * width;
    const y = height - ((lat - b.minLat) / (b.maxLat - b.minLat)) * height;
    return [x, y];
  };

  AE.focusMap.ringToPath = function (ring, width, height, bounds, mode) {
    const projectFn = mode === "drill" ? AE.focusMap.projectDrill : AE.focusMap.project;
    return (
      ring
        .map((pt, i) => {
          const [x, y] = projectFn(pt[0], pt[1], width, height, bounds);
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
