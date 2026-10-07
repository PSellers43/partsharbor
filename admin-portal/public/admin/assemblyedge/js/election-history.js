/* AssemblyEdge — precinct election history loader (Focus drill overlay) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.electionHistory = AE.electionHistory || {};
  AE.electionHistoryIndex = null;
  AE.electionHistoryLoadError = null;
  AE.electionPrecinctGeo = AE.electionPrecinctGeo || {};
  AE.electionPrecinctLoadError = AE.electionPrecinctLoadError || {};

  const RACE_LABELS = {
    g22_asm: "2022 General · Assembly",
    g24_asm: "2024 General · Assembly",
  };

  AE.electionHistory.raceLabel = function (raceId) {
    return RACE_LABELS[raceId] || raceId;
  };

  AE.electionHistory.loadIndex = function () {
    AE.electionHistoryIndex = null;
    AE.electionHistoryLoadError = null;
    return fetch("data/election-history/latest/election-history-index.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.electionHistoryIndex = json;
      })
      .catch((err) => {
        AE.electionHistoryLoadError = String(err && err.message ? err.message : err);
      });
  };

  AE.electionHistory.districtMeta = function (districtId) {
    const root = AE.electionHistoryIndex;
    if (!root || !Array.isArray(root.districts)) return null;
    return root.districts.find((d) => d.id === districtId) || null;
  };

  AE.electionHistory.loadPrecincts = function (districtId) {
    if (AE.electionPrecinctGeo[districtId]) return Promise.resolve(AE.electionPrecinctGeo[districtId]);
    const meta = AE.electionHistory.districtMeta(districtId);
    if (!meta || !meta.file) {
      AE.electionPrecinctLoadError[districtId] = "No election history layer for this district.";
      return Promise.resolve(null);
    }
    AE.electionPrecinctLoadError[districtId] = null;
    return fetch("data/election-history/latest/" + meta.file, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        json._bounds = AE.focusMap.computeBounds({ features: json.features || [] });
        AE.electionPrecinctGeo[districtId] = json;
        return json;
      })
      .catch((err) => {
        AE.electionPrecinctLoadError[districtId] = String(err && err.message ? err.message : err);
        return null;
      });
  };

  /** Two-party Dem margin in points (+ = Dem lead). */
  AE.electionHistory.marginBand = function (marginDem) {
    if (marginDem == null || Number.isNaN(Number(marginDem))) {
      return { label: "No data", class: "margin-nodata", color: "#3a3f47" };
    }
    const m = Number(marginDem);
    if (m >= 20) return { label: "D+" + Math.round(m), class: "margin-strong-d", color: "#1e5a9e" };
    if (m >= 8) return { label: "D+" + Math.round(m), class: "margin-lean-d", color: "#5c8fd4" };
    if (m > -8) return { label: (m >= 0 ? "D+" : "R+") + Math.abs(Math.round(m)), class: "margin-tossup", color: "#7a8494" };
    if (m > -20) return { label: "R+" + Math.abs(Math.round(m)), class: "margin-lean-r", color: "#c45c5c" };
    return { label: "R+" + Math.abs(Math.round(m)), class: "margin-strong-r", color: "#8b2323" };
  };

  AE.electionHistory.attributionHtml = function (districtId, raceId) {
    const geo = AE.electionPrecinctGeo[districtId];
    const idx = AE.electionHistoryIndex;
    if (!geo || !geo.source) {
      return "Public SR precinct results · UC Berkeley Statewide Database (not a voter file).";
    }
    const race = (geo.source.races && geo.source.races[raceId]) || {};
    const built = geo.source.built_at || "—";
    const swdb =
      idx && idx.sources && idx.sources.swdb_g24
        ? `<a href="${idx.sources.swdb_g24}" target="_blank" rel="noopener">SWDB</a>`
        : "SWDB";
    return (
      `Election history: ${race.label || AE.electionHistory.raceLabel(raceId)} · ${swdb} SR precinct SOV + boundaries. ` +
      `Built ${built}. Two-party Assembly margin (Dem − Rep share).`
    );
  };

  AE.electionHistory.precinctPaths = function (districtId, width, height, raceId, filterBands) {
    const geo = AE.electionPrecinctGeo[districtId];
    if (!geo || !geo.features) return { outline: "", precincts: [] };
    const bounds = geo._bounds || AE.focusDrill.bounds(districtId);
    const precincts = [];

    (geo.features || []).forEach((f) => {
      const p = f.properties || {};
      const race = p[raceId];
      const margin = race && race.margin_dem != null ? race.margin_dem : null;
      const band = AE.electionHistory.marginBand(margin);
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
      precincts.push({
        id: p.precinct_id || p.srprec,
        srprec: p.srprec,
        d: d.trim(),
        margin,
        demPct: race && race.dem_pct != null ? race.dem_pct : null,
        votes: race && race.votes_two_party != null ? race.votes_two_party : null,
        band,
        hasData: margin != null,
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

    return { outline: outline.trim(), precincts };
  };
})();
