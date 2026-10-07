/* MajorityIQ — precinct election history loader (Focus drill overlay) */

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

  const MAP_W = 400;
  const MAP_H = 480;

  AE.electionHistory.raceLabel = function (raceId) {
    return RACE_LABELS[raceId] || raceId;
  };

  function indexGeojson(districtId, json) {
    json._byPrecinctId = {};
    (json.features || []).forEach((f) => {
      const p = f.properties || {};
      const id = p.precinct_id || p.srprec;
      if (id) json._byPrecinctId[id] = p;
    });
  }

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
        indexGeojson(districtId, json);
        AE.electionPrecinctGeo[districtId] = json;
        return json;
      })
      .catch((err) => {
        AE.electionPrecinctLoadError[districtId] = String(err && err.message ? err.message : err);
        return null;
      });
  };

  AE.electionHistory.precinctProps = function (districtId, precinctId) {
    const geo = AE.electionPrecinctGeo[districtId];
    if (!geo || !geo._byPrecinctId) return null;
    return geo._byPrecinctId[precinctId] || null;
  };

  /** Choropleth band (map fill + legend filters). */
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

  /** Pill styling for rank list, tooltip, and detail card (D blue / R red / tie gray). */
  AE.electionHistory.marginChipMeta = function (marginDem) {
    if (marginDem == null || Number.isNaN(Number(marginDem))) {
      return { label: "No data", chipClass: "margin-chip-nodata" };
    }
    const m = Number(marginDem);
    if (Math.abs(m) < 0.5) {
      return { label: "Even", chipClass: "margin-chip-tie" };
    }
    const label = (m >= 0 ? "D+" : "R+") + Math.abs(Math.round(m));
    let chipClass;
    if (m > 0) chipClass = m >= 8 ? "margin-chip-d-strong" : "margin-chip-d-lean";
    else chipClass = m <= -8 ? "margin-chip-r-strong" : "margin-chip-r-lean";
    return { label, chipClass };
  };

  AE.electionHistory.marginChipHtml = function (marginDem) {
    const meta = AE.electionHistory.marginChipMeta(marginDem);
    return `<span class="margin-chip ${meta.chipClass}">${meta.label}</span>`;
  };

  AE.electionHistory.formatSwing = function (margin22, margin24) {
    if (margin22 == null || margin24 == null || Number.isNaN(margin22) || Number.isNaN(margin24)) {
      return "—";
    }
    const shift = Number(margin24) - Number(margin22);
    const toward = shift > 0 ? "D" : shift < 0 ? "R" : "even";
    const pts = Math.abs(Math.round(shift * 10) / 10);
    if (toward === "even" || pts < 0.05) return "No net shift";
    return pts + "-pt swing toward " + toward;
  };

  AE.electionHistory.precinctRankTitle = function (row) {
    const id = row.srprec || row.id;
    const place = row.placePrimary;
    return place ? `Precinct ${id} · ${place}` : `Precinct ${id}`;
  };

  AE.electionHistory.viewBoxForBbox = function (bbox, padRatio) {
    if (!bbox || bbox.length !== 4) return null;
    const pad = padRatio != null ? padRatio : 0.12;
    const [minLon, minLat, maxLon, maxLat] = bbox;
    const wLon = maxLon - minLon || 0.02;
    const hLat = maxLat - minLat || 0.02;
    const pxLon = wLon * (1 + pad * 2);
    const pxLat = hLat * (1 + pad * 2);
    const cx = (minLon + maxLon) / 2;
    const cy = (minLat + maxLat) / 2;
    const aspect = MAP_W / MAP_H;
    let viewW = pxLon;
    let viewH = pxLat;
    if (viewW / viewH > aspect) viewH = viewW / aspect;
    else viewW = viewH * aspect;
    const minX = cx - viewW / 2;
    const minY = cy - viewH / 2;
    return {
      minLon: minX,
      minLat: minY,
      maxLon: minX + viewW,
      maxLat: minY + viewH,
      viewBox: `0 0 ${MAP_W} ${MAP_H}`,
    };
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
    const places =
      idx && idx.sources && idx.sources.census_places
        ? ` · City/town labels: <a href="${idx.sources.census_places}" target="_blank" rel="noopener">Census TIGER places</a>`
        : geo.source.places
          ? " · City/town labels: U.S. Census TIGER/Line places"
          : "";
    return (
      `Election history: ${race.label || AE.electionHistory.raceLabel(raceId)} · ${swdb} SR precinct SOV + boundaries${places}. ` +
      `Built ${built}. Two-party Assembly margin (Dem − Rep share).`
    );
  };

  function propsToRow(p, raceId, d, band) {
    const race = p[raceId];
    const margin = race && race.margin_dem != null ? race.margin_dem : null;
    return {
      id: p.precinct_id || p.srprec,
      srprec: p.srprec,
      d: d,
      margin,
      demPct: race && race.dem_pct != null ? race.dem_pct : null,
      votes: race && race.votes_two_party != null ? race.votes_two_party : null,
      band,
      hasData: margin != null,
      placePrimary: p.place_primary || null,
      placeAlso: p.place_also || [],
      countyName: p.county_name || null,
      areaSqMi: p.area_sq_mi != null ? p.area_sq_mi : null,
      places: p.places || [],
      bbox: p.bbox || null,
      g22: p.g22_asm || null,
      g24: p.g24_asm || null,
    };
  }

  AE.electionHistory.precinctPaths = function (districtId, width, height, raceId, filterBands, boundsOverride) {
    const geo = AE.electionPrecinctGeo[districtId];
    if (!geo || !geo.features) return { outline: "", precincts: [] };
    const bounds = boundsOverride || geo._bounds || AE.focusDrill.bounds(districtId);
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
      precincts.push(propsToRow(p, raceId, d.trim(), band));
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

    return { outline: outline.trim(), precincts, bounds };
  };

  AE.electionHistory.tooltipHtml = function (row, raceId) {
    if (!row) return "";
    const also =
      row.placeAlso && row.placeAlso.length
        ? `<div class="precinct-tooltip-also">also: ${row.placeAlso.slice(0, 3).join(", ")}</div>`
        : "";
    const county = row.countyName ? `<div class="precinct-tooltip-county">${row.countyName} County</div>` : "";
    const meta =
      row.demPct != null
        ? `<div class="precinct-tooltip-votes">${row.demPct}% two-party Dem · ${row.votes != null ? row.votes.toLocaleString() + " votes" : ""}</div>`
        : "";
    return (
      `<div class="precinct-tooltip-title">Precinct ${row.srprec || row.id}</div>` +
      (row.placePrimary ? `<div class="precinct-tooltip-place">${row.placePrimary}</div>` : "") +
      also +
      county +
      `<div class="precinct-tooltip-margin">${AE.electionHistory.marginChipHtml(row.margin)}</div>` +
      meta
    );
  };

  AE.electionHistory.detailCardHtml = function (row, selectedRaceId) {
    if (!row) return "";
    const placesList =
      row.places && row.places.length
        ? row.places
            .map((pl) => `<li><span>${pl.name}</span><span>${pl.pct}% of area</span></li>`)
            .join("")
        : row.placePrimary
          ? `<li><span>${row.placePrimary}</span><span>—</span></li>`
          : "";

    const g22 = row.g22;
    const g24 = row.g24;
    const swing = AE.electionHistory.formatSwing(g22 && g22.margin_dem, g24 && g24.margin_dem);

    function raceBlock(label, race) {
      if (!race || race.margin_dem == null) {
        return `<div class="precinct-detail-race"><span class="precinct-detail-race-label">${label}</span><span class="precinct-detail-race-empty">No data</span></div>`;
      }
      const votes = race.votes_two_party != null ? race.votes_two_party.toLocaleString() + " votes" : "";
      const winner = race.winner ? ` · ${race.winner} lead` : "";
      return (
        `<div class="precinct-detail-race">` +
        `<span class="precinct-detail-race-label">${label}</span>` +
        AE.electionHistory.marginChipHtml(race.margin_dem) +
        `<span class="precinct-detail-race-meta">${race.dem_pct != null ? race.dem_pct + "% Dem" : ""}${winner}${votes ? " · " + votes : ""}</span>` +
        `</div>`
      );
    }

    const contestNote =
      selectedRaceId === "g22_asm"
        ? "Map colors use 2022 contest when selected."
        : selectedRaceId === "g24_asm"
          ? "Map colors use 2024 contest when selected."
          : "";

    return (
      `<div class="precinct-detail-head">` +
      `<div><h4 class="precinct-detail-title">Precinct ${row.srprec || row.id}</h4>` +
      (row.placePrimary ? `<p class="precinct-detail-sub">${row.placePrimary}</p>` : "") +
      `</div>` +
      `<button type="button" class="precinct-detail-close" aria-label="Close precinct detail">×</button>` +
      `</div>` +
      `<dl class="precinct-detail-facts">` +
      (row.countyName ? `<div><dt>County</dt><dd>${row.countyName}</dd></div>` : "") +
      (row.areaSqMi != null ? `<div><dt>Area</dt><dd>${row.areaSqMi} sq mi</dd></div>` : "") +
      `</dl>` +
      (placesList ? `<p class="precinct-detail-section-label">Places in precinct</p><ul class="precinct-detail-places">${placesList}</ul>` : "") +
      `<p class="precinct-detail-section-label">Assembly margin (two-party)</p>` +
      `<div class="precinct-detail-races">${raceBlock("2022 General", g22)}${raceBlock("2024 General", g24)}</div>` +
      `<p class="precinct-detail-swing">${swing}</p>` +
      (contestNote ? `<p class="precinct-detail-note">${contestNote}</p>` : "")
    );
  };

  AE.electionHistory.searchHaystack = function (row) {
    const parts = [row.srprec, row.id, row.placePrimary].concat(row.placeAlso || []);
    if (row.places) row.places.forEach((pl) => parts.push(pl.name));
    return parts.filter(Boolean).join(" ").toLowerCase();
  };
})();
