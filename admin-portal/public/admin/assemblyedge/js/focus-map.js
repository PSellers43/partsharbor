/* AssemblyEdge — focus / opportunity score + map helpers */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.focusMap = AE.focusMap || {};
  AE.mapGeo = null;
  AE.mapGeoLoadError = null;

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
    return fetch("data/map/beachhead-districts.geojson", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.mapGeo = json;
        AE.mapGeoLoadError = null;
      })
      .catch((err) => {
        AE.mapGeo = null;
        AE.mapGeoLoadError = String(err && err.message ? err.message : err);
      });
  };

  /** Web Mercator-ish project for CA lon/lat → SVG (static viewBox). */
  AE.focusMap.project = function (lon, lat, width, height, bounds) {
    const b = bounds || { minLon: -124.5, maxLon: -114, minLat: 32.4, maxLat: 42.2 };
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

  AE.focusMap.featurePaths = function (width, height) {
    if (!AE.mapGeo || !AE.mapGeo.features) return [];
    const bounds = { minLon: -124.5, maxLon: -114, minLat: 32.4, maxLat: 42.2 };
    return AE.mapGeo.features.map((f) => {
      const distNo = f.properties.dist_no;
      const id = f.properties.id || "ad-" + distNo;
      const paths = [];
      const geom = f.geometry;
      if (geom.type === "Polygon") {
        geom.coordinates.forEach((ring) => paths.push(AE.focusMap.ringToPath(ring, width, height, bounds)));
      } else if (geom.type === "MultiPolygon") {
        geom.coordinates.forEach((poly) => poly.forEach((ring) => paths.push(AE.focusMap.ringToPath(ring, width, height, bounds))));
      }
      const { score } = AE.focusMap.computeScore(id);
      const band = AE.focusMap.scoreBand(score);
      return { id, code: f.properties.code, distNo, d: paths.join(" "), score, band };
    });
  };
})();
