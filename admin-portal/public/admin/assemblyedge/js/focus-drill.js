/* AssemblyEdge — intra-district focus drill-down (cities / CDPs) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.focusDrill = AE.focusDrill || {};
  AE.intraGeo = AE.intraGeo || {};
  AE.intraGeoLoadError = AE.intraGeoLoadError || {};

  const BEACHHEAD_IDS = ["ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"];

  AE.focusDrill.isBeachhead = function (districtId) {
    return BEACHHEAD_IDS.indexOf(districtId) >= 0;
  };

  AE.focusDrill.parseHash = function () {
    const raw = (window.location.hash || "").replace(/^#/, "");
    if (!raw) return { page: null, districtId: null };
    if (raw === "focus-map") return { page: "focus-map", districtId: null };
    const m = /^focus-map\/(ad-\d+)$/i.exec(raw);
    if (m) return { page: "focus-map", districtId: m[1].toLowerCase() };
    return { page: null, districtId: null };
  };

  AE.focusDrill.setHash = function (districtId) {
    const next = districtId ? "#focus-map/" + districtId : "#focus-map";
    if (window.location.hash !== next) {
      history.pushState(null, "", next);
    }
  };

  AE.focusDrill.loadIntra = function (districtId) {
    if (!AE.focusDrill.isBeachhead(districtId)) {
      AE.intraGeoLoadError[districtId] = "No intra-district layer for this AD yet.";
      return Promise.resolve(null);
    }
    if (AE.intraGeo[districtId]) return Promise.resolve(AE.intraGeo[districtId]);
    AE.intraGeoLoadError[districtId] = null;
    const distNo = districtId.replace("ad-", "");
    return fetch("data/map/intra/ad-" + distNo + ".geojson", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        json._bounds = AE.focusMap.computeBounds({ features: json.features || [] });
        AE.intraGeo[districtId] = json;
        return json;
      })
      .catch((err) => {
        AE.intraGeoLoadError[districtId] = String(err && err.message ? err.message : err);
        return null;
      });
  };

  AE.focusDrill.bounds = function (districtId) {
    const g = AE.intraGeo[districtId];
    if (g && g._bounds) return g._bounds;
    return AE.focusMap.bounds();
  };

  AE.focusDrill.attributionHtml = function (districtId) {
    const g = AE.intraGeo[districtId];
    if (!g || !g.source) {
      return "Places clipped to CRC 2020 Assembly boundary · scores from public 2022 g22 data (illustrative).";
    }
    const s = g.source;
    return (
      `Intra-district layer: ${s.places || "Census places"} · ${s.election || "SWDB g22"}. ` +
      `Built ${s.built_at || "—"}. ${s.score_formula || ""}`
    );
  };

  AE.focusDrill.placePaths = function (districtId, width, height, filterBands) {
    const geo = AE.intraGeo[districtId];
    if (!geo || !geo.features) return { outline: "", places: [] };
    const bounds = AE.focusDrill.bounds(districtId);
    const places = [];

    (geo.features || []).forEach((f) => {
      const p = f.properties || {};
      const score = typeof p.focus_score === "number" ? p.focus_score : 0;
      const band = AE.focusMap.scoreBand(score);
      if (filterBands && !filterBands[band.class]) return;

      const geom = f.geometry;
      let d = "";
      if (geom.type === "Polygon") {
        geom.coordinates.forEach((ring) => {
          d += AE.focusMap.ringToPath(ring, width, height, bounds) + " ";
        });
      } else if (geom.type === "MultiPolygon") {
        geom.coordinates.forEach((poly) => {
          poly.forEach((ring) => {
            d += AE.focusMap.ringToPath(ring, width, height, bounds) + " ";
          });
        });
      }
      places.push({
        id: p.geoid || p.name,
        name: p.name,
        kind: p.kind,
        d: d.trim(),
        score,
        band,
        demPct: p.dem_pct_2022_asm,
        turnoutPct: p.turnout_pct_2022,
        hasData: !!p.has_election_data,
      });
    });

    let outline = "";
    if (geo.outline) {
      const og = geo.outline;
      if (og.type === "Polygon") {
        og.coordinates.forEach((ring) => {
          outline += AE.focusMap.ringToPath(ring, width, height, bounds) + " ";
        });
      }
    }

    return { outline: outline.trim(), places };
  };
})();
