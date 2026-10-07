/* MajorityIQ — public polling loader + gap helpers */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.polling = AE.polling || {};
  AE.pollingData = null;
  AE.pollingLoadError = null;

  function parseDate(iso) {
    if (!iso) return null;
    const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function daysBetween(a, b) {
    const ms = 86400000;
    return Math.floor((b.getTime() - a.getTime()) / ms);
  }

  AE.polling.getGapDays = function () {
    const root = AE.pollingData;
    return root && root.gap_recent_days ? root.gap_recent_days : 90;
  };

  AE.polling.districtRow = function (districtId) {
    const root = AE.pollingData;
    if (!root || !Array.isArray(root.districts)) return null;
    return root.districts.find((d) => d.id === districtId) || null;
  };

  AE.polling.isRecent = function (poll, asOfDate) {
    if (!poll || !poll.field_end) return false;
    const end = parseDate(poll.field_end);
    const asOf = asOfDate || new Date();
    if (!end) return false;
    return daysBetween(end, asOf) <= AE.polling.getGapDays();
  };

  AE.polling.daysSincePoll = function (poll, asOfDate) {
    if (!poll || !poll.field_end) return null;
    const end = parseDate(poll.field_end);
    const asOf = asOfDate || new Date();
    if (!end) return null;
    return daysBetween(end, asOf);
  };

  AE.polling.load = function () {
    AE.pollingData = null;
    AE.pollingLoadError = null;
    return fetch("data/polling/latest.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then((json) => {
        AE.pollingData = json;
        AE.pollingLoadError = null;
      })
      .catch((err) => {
        AE.pollingData = null;
        AE.pollingLoadError = String(err && err.message ? err.message : err);
      });
  };

  AE.polling.gapSeverity = function (districtId) {
    const row = AE.polling.districtRow(districtId);
    if (!row) return 1;
    const poll = row.poll;
    if (poll && AE.polling.isRecent(poll)) return 0.15;
    if (poll) return 0.55;
    return 1;
  };
})();
