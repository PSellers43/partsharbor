/* AssemblyEdge — Campaign Manager layer (localStorage decision log + checklist) */

(function () {
  "use strict";

  const LS_LOG = "ae-cm-decision-log";
  const LS_CHECK = "ae-cm-checklist";
  const LS_MODE = "ae-cm-race-mode";
  const LS_ROLE = "ae-role";

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }
  function saveJSON(key, val) {
    localStorage.setItem(key, JSON.stringify(val));
  }

  function todayKey() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function getRole() {
    return localStorage.getItem(LS_ROLE) || "analyst";
  }
  function setRole(role) {
    localStorage.setItem(LS_ROLE, role === "cm" ? "cm" : "analyst");
  }

  function getRaceMode() {
    return localStorage.getItem(LS_MODE) || "persuasion";
  }
  function setRaceMode(mode) {
    localStorage.setItem(LS_MODE, mode === "turnout" ? "turnout" : "persuasion");
  }

  function getChecklist() {
    const all = loadJSON(LS_CHECK, {});
    const key = todayKey();
    if (!all[key]) all[key] = {};
    return { key, map: all[key], store: all };
  }
  function toggleCheck(id) {
    const { key, map, store } = getChecklist();
    map[id] = !map[id];
    store[key] = map;
    saveJSON(LS_CHECK, store);
    return !!map[id];
  }

  function getLog() {
    return loadJSON(LS_LOG, []);
  }
  function addLogEntry(entry) {
    const log = getLog();
    log.unshift(entry);
    saveJSON(LS_LOG, log.slice(0, 80));
    return log;
  }
  function clearLog() {
    saveJSON(LS_LOG, []);
  }

  function evidenceChips(ids) {
    return (ids || [])
      .map((id) => {
        const d = AE.doctrine.find((x) => x.id === id);
        if (!d) return "";
        return `<span class="chip chip-evidence" title="${escapeAttr(d.principle)}">${escapeHtml(d.cite)}</span>`;
      })
      .join(" ");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function urgencyClass(u) {
    if (u === "high") return "cm-urgency-high";
    if (u === "medium") return "cm-urgency-med";
    return "cm-urgency-low";
  }

  AE.CM = {
    getRole,
    setRole,
    getRaceMode,
    setRaceMode,
    getChecklist,
    toggleCheck,
    getLog,
    addLogEntry,
    clearLog,
    evidenceChips,
    todayKey,
    urgencyClass,
    escapeHtml,
  };
})();
