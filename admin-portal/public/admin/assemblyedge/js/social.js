/* MajorityIQ — X social digest (read-only; loaded from session API or bundled seed) */

window.AE = window.AE || {};

(function () {
  "use strict";

  AE.social = AE.social || {};

  const FLAG_ORDER = ["attack", "ad", "endorsement", "spike", "event", "policy", "fundraising"];
  const FLAG_LABELS = {
    attack: "Attack",
    ad: "Ad",
    endorsement: "Endorsement",
    spike: "Spike",
    event: "Event",
    policy: "Policy",
    fundraising: "Fundraising",
  };

  AE.socialData = null;
  AE.socialMeta = null;
  AE.socialLoadError = null;

  const MIN_SIDE_N = 2;
  const CHART_DAYS = 14;
  const SENTIMENT_LABELS = { positive: "Positive", neutral: "Neutral", negative: "Negative" };

  function escapeHtml(s) {
    if (AE.CM && AE.CM.escapeHtml) return AE.CM.escapeHtml(s);
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function apiBase() {
    const path = window.location.pathname || "";
    if (path.indexOf("/admin/majorityiq") === 0) return "/admin/majorityiq";
    if (path.indexOf("/admin/assemblyedge") === 0) return "/admin/assemblyedge";
    return "/admin/majorityiq";
  }

  function districtIdToCode(districtId) {
    const m = /^ad-(\d+)$/i.exec(districtId || "");
    return m ? "AD-" + parseInt(m[1], 10) : null;
  }

  function districtCodeToId(code) {
    const m = /^AD-(\d+)$/i.exec(code || "");
    return m ? "ad-" + parseInt(m[1], 10) : null;
  }

  function districtBlock(districtId) {
    const code = districtIdToCode(districtId);
    if (!AE.socialData || !code) return null;
    return AE.socialData.districts && AE.socialData.districts[code];
  }

  function parsePostDate(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function relativeTime(iso) {
    const d = parsePostDate(iso);
    if (!d) return iso || "—";
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return "just now";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
    if (sec < 604800) return Math.floor(sec / 86400) + "d ago";
    try {
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/Los_Angeles" });
    } catch {
      return iso;
    }
  }

  function formatAsOf(iso) {
    const d = parsePostDate(iso);
    if (!d) return iso || "—";
    try {
      return d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "America/Los_Angeles",
        timeZoneName: "short",
      });
    } catch {
      return iso;
    }
  }

  function flagPriority(flags) {
    if (!flags || !flags.length) return 999;
    let best = 999;
    flags.forEach((f) => {
      const idx = FLAG_ORDER.indexOf(f);
      if (idx >= 0 && idx < best) best = idx;
    });
    return best;
  }

  function historyForDistrict(districtId, maxDays) {
    const code = districtIdToCode(districtId);
    if (!AE.socialData || !code) return [];
    const rows = (AE.socialData.sentiment_history || []).filter((r) => r.district === code);
    rows.sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const limit = maxDays != null ? maxDays : CHART_DAYS;
    return rows.slice(-limit);
  }

  function chartHasEnoughData(rows) {
    if (!rows || rows.length < 2) return false;
    let scoredDays = 0;
    rows.forEach((r) => {
      const n =
        ((r.candidate_posts && r.candidate_posts.n) || 0) +
        ((r.mentions && r.mentions.n) || 0);
      if (n > 0) scoredDays += 1;
    });
    return scoredDays >= 2;
  }

  function svgLineChart(rows, opts) {
    opts = opts || {};
    const w = opts.width || 320;
    const h = opts.height || opts.compact ? 36 : 132;
    const pad = opts.compact ? { t: 4, r: 4, b: 4, l: 4 } : { t: 12, r: 12, b: 28, l: 36 };
    const innerW = w - pad.l - pad.r;
    const innerH = h - pad.t - pad.b;
    if (!rows.length) {
      return `<svg class="social-sentiment-svg social-sentiment-empty" viewBox="0 0 ${w} ${h}" role="img" aria-label="No sentiment history"></svg>`;
    }
    const xStep = rows.length > 1 ? innerW / (rows.length - 1) : 0;
    const yScale = (v) => pad.t + innerH * (1 - (v + 1) / 2);

    const volMax = Math.max(
      1,
      ...rows.map((r) => ((r.candidate_posts && r.candidate_posts.n) || 0) + ((r.mentions && r.mentions.n) || 0))
    );

    let bars = "";
    rows.forEach((r, i) => {
      const vol = ((r.candidate_posts && r.candidate_posts.n) || 0) + ((r.mentions && r.mentions.n) || 0);
      const bh = (vol / volMax) * innerH * 0.35;
      const x = pad.l + i * xStep - (opts.compact ? 1 : 3);
      bars += `<rect class="social-vol-bar" x="${x}" y="${pad.t + innerH - bh}" width="${opts.compact ? 3 : 6}" height="${bh}" opacity="0.18"><title>${escapeHtml(r.date)} · ${vol} scored post(s)</title></rect>`;
    });

    function poly(side, cls) {
      const pts = [];
      rows.forEach((r, i) => {
        const bucket = r[side];
        if (!bucket || bucket.n < 1 || bucket.avg == null) return;
        const x = pad.l + i * xStep;
        pts.push(`${x},${yScale(bucket.avg)}`);
      });
      if (pts.length < 2) return "";
      return `<polyline class="${cls}" fill="none" points="${pts.join(" ")}" />`;
    }

    function polyNet(cls) {
      const pts = [];
      rows.forEach((r, i) => {
        if (r.net == null) return;
        const x = pad.l + i * xStep;
        pts.push(`${x},${yScale(Math.max(-1, Math.min(1, r.net)))}`);
      });
      if (pts.length < 2) return "";
      return `<polyline class="${cls}" fill="none" points="${pts.join(" ")}" />`;
    }

    let dots = "";
    if (!opts.compact) {
      rows.forEach((r, i) => {
        ["toward_r", "toward_d"].forEach((side) => {
          const bucket = r[side];
          if (!bucket || bucket.n < 1 || bucket.avg == null) return;
          const x = pad.l + i * xStep;
          const y = yScale(bucket.avg);
          const label = side === "toward_r" ? "R-side" : "D-side";
          dots += `<circle class="social-sent-dot social-sent-dot-${side === "toward_r" ? "r" : "d"}" cx="${x}" cy="${y}" r="3"><title>${escapeHtml(r.date)} · ${label} tone ${bucket.avg} (n=${bucket.n})</title></circle>`;
        });
      });
    }

    let axis = "";
    if (!opts.compact) {
      axis += `<line class="social-sent-axis" x1="${pad.l}" y1="${yScale(0)}" x2="${pad.l + innerW}" y2="${yScale(0)}" />`;
      axis += `<text class="social-sent-y-label" x="${pad.l - 6}" y="${yScale(1) + 3}" text-anchor="end">+1</text>`;
      axis += `<text class="social-sent-y-label" x="${pad.l - 6}" y="${yScale(0) + 3}" text-anchor="end">0</text>`;
      axis += `<text class="social-sent-y-label" x="${pad.l - 6}" y="${yScale(-1) + 3}" text-anchor="end">−1</text>`;
      const first = rows[0].date && rows[0].date.slice(5);
      const last = rows[rows.length - 1].date && rows[rows.length - 1].date.slice(5);
      axis += `<text class="social-sent-x-label" x="${pad.l}" y="${h - 6}">${escapeHtml(first || "")}</text>`;
      axis += `<text class="social-sent-x-label" x="${pad.l + innerW}" y="${h - 6}" text-anchor="end">${escapeHtml(last || "")}</text>`;
    }

    const lines = opts.compact
      ? polyNet("social-sent-line-net")
      : poly("toward_r", "social-sent-line-r") + poly("toward_d", "social-sent-line-d");
    return `<svg class="social-sentiment-svg${opts.compact ? " social-sentiment-svg-compact" : ""}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Daily sentiment trend">${bars}${axis}${lines}${dots}</svg>`;
  }

  function renderSentimentChartSection(districtId) {
    const rows = historyForDistrict(districtId, CHART_DAYS);
    const enough = chartHasEnoughData(rows);
    const latest = rows.length ? rows[rows.length - 1] : null;
    const lowSample =
      latest &&
      ((latest.toward_r && latest.toward_r.n > 0 && latest.toward_r.n < MIN_SIDE_N) ||
        (latest.toward_d && latest.toward_d.n > 0 && latest.toward_d.n < MIN_SIDE_N));

    if (!enough) {
      return `
        <section class="social-sentiment-wrap" aria-label="Daily sentiment trend">
          <h4 class="social-subtitle">Daily sentiment trend</h4>
          <div class="social-sentiment-note social-sentiment-thin">
            <span class="chip chip-demo">Not enough data</span>
            Need at least two days with scored posts in the last ${CHART_DAYS} days. Scores are AI-estimated tone from public X text — not polling.
          </div>
        </section>`;
    }

    return `
      <section class="social-sentiment-wrap" aria-label="Daily sentiment trend">
        <h4 class="social-subtitle">Daily sentiment trend</h4>
        <p class="social-sentiment-note">AI-estimated tone from public X posts and mentions (−1 negative → +1 positive). <strong>Not polling.</strong> Faint bars = scored post count that day.</p>
        ${
          lowSample
            ? `<p class="social-sentiment-note social-sentiment-thin"><span class="chip chip-demo">Low sample</span> Side sample size under ${MIN_SIDE_N} on the latest day — interpret with caution.</p>`
            : ""
        }
        <div class="social-sentiment-legend">
          <span class="social-legend-r">R-side tone</span>
          <span class="social-legend-d">D-side tone</span>
        </div>
        <div class="social-sentiment-chart">${svgLineChart(rows, { width: 320, height: 132, compact: false })}</div>
      </section>`;
  }

  AE.social.renderBoardSparklines = function () {
    if (!AE.socialData || AE.socialLoadError) {
      return `<p class="intel-teaser-desc">Sentiment sparklines unavailable.</p>`;
    }
    const districts = (AE.districts || []).slice().sort((a, b) => a.code.localeCompare(b.code));
    return `
      <div class="social-board-spark-grid" role="list">
        ${districts
          .map((d) => {
            const rows = historyForDistrict(d.id, CHART_DAYS);
            const nets = rows.map((r) => (r.net != null ? r.net : null)).filter((v) => v != null);
            const trend =
              nets.length >= 2 ? (nets[nets.length - 1] > nets[0] ? "↑" : nets[nets.length - 1] < nets[0] ? "↓" : "→") : "—";
            const latestNet = nets.length ? nets[nets.length - 1] : null;
            return `
              <button type="button" class="social-spark-cell" data-district-social-open="${d.id}" role="listitem">
                <span class="social-spark-code">${escapeHtml(d.code)}</span>
                <span class="social-spark-net">${latestNet != null ? (latestNet >= 0 ? "+" : "") + latestNet.toFixed(2) : "n/a"} ${trend}</span>
                ${svgLineChart(rows, { width: 120, height: 36, compact: true })}
              </button>`;
          })
          .join("")}
      </div>`;
  };

  AE.social.sentimentTrendSummary = function (districtId) {
    const rows = historyForDistrict(districtId, CHART_DAYS);
    if (!rows.length) {
      return { ok: false, summary: "No sentiment history rows for this district." };
    }
    const withNet = rows.filter((r) => r.net != null);
    if (withNet.length < 2) {
      return { ok: false, summary: "Not enough days with net sentiment to describe a trend." };
    }
    const first = withNet[0];
    const last = withNet[withNet.length - 1];
    const delta = Math.round((last.net - first.net) * 1000) / 1000;
    const dir = delta > 0.05 ? "toward R-side tone" : delta < -0.05 ? "toward D-side tone" : "flat";
    return {
      ok: true,
      summary: `Net sentiment (${last.date}) ${last.net >= 0 ? "+" : ""}${last.net} vs ${first.date} ${first.net >= 0 ? "+" : ""}${first.net} (Δ ${delta >= 0 ? "+" : ""}${delta}) — trending ${dir}. Based on AI-estimated tone from public X posts, not polling.`,
      rows: withNet.slice(-8).map((r) => ({
        date: r.date,
        net: r.net,
        toward_r: r.toward_r && r.toward_r.avg,
        toward_d: r.toward_d && r.toward_d.avg,
        n:
          ((r.candidate_posts && r.candidate_posts.n) || 0) + ((r.mentions && r.mentions.n) || 0),
      })),
    };
  };

  function sentimentChip(post) {
    if (post.sentiment == null || !post.sentiment_label) return "";
    const lab = SENTIMENT_LABELS[post.sentiment_label] || post.sentiment_label;
    return `<span class="chip chip-sentiment-${post.sentiment_label}">${escapeHtml(lab)} ${post.sentiment >= 0 ? "+" : ""}${post.sentiment}</span>`;
  }

  function pickNotablePost(posts) {
    if (!posts || !posts.length) return null;
    const sorted = posts.slice().sort((a, b) => {
      const pa = flagPriority(a.flags);
      const pb = flagPriority(b.flags);
      if (pa !== pb) return pa - pb;
      const da = parsePostDate(a.created_at);
      const db = parsePostDate(b.created_at);
      return (db ? db.getTime() : 0) - (da ? da.getTime() : 0);
    });
    const top = sorted[0];
    if (!top.flags || !top.flags.length) return null;
    return top;
  }

  AE.social.boardLine = function (districtId) {
    if (AE.socialLoadError) {
      return `<span class="social-board-line">X feed unavailable.</span>`;
    }
    if (!AE.socialData) {
      return `<span class="social-board-line">X feed loading…</span>`;
    }
    const block = districtBlock(districtId);
    const posts = (block && block.posts) || [];
    const notable = pickNotablePost(posts);
    if (notable) {
      const flag = (notable.flags && notable.flags[0]) || "";
      const chip = flag ? `<span class="chip chip-social-flag chip-flag-${flag}">${escapeHtml(FLAG_LABELS[flag] || flag)}</span> ` : "";
      return `<span class="social-board-line">${chip}<strong>${escapeHtml(notable.candidate || "—")}</strong>: ${escapeHtml(notable.summary || notable.text || "")}</span>`;
    }
    if (!posts.length) {
      return `<span class="social-board-line social-board-quiet">Quiet on X this week.</span>`;
    }
    return `<span class="social-board-line social-board-quiet">Quiet on X this week (no flagged posts).</span>`;
  };

  AE.social.briefBullet = function (districtId) {
    if (!AE.socialData || AE.socialLoadError) return null;
    const block = districtBlock(districtId);
    const posts = (block && block.posts) || [];
    const notable = pickNotablePost(posts);
    const asOf = formatAsOf(AE.socialData.as_of);
    if (notable) {
      const flags = (notable.flags || []).map((f) => FLAG_LABELS[f] || f).join(", ");
      return `X signal (${asOf}): ${notable.candidate} — ${notable.summary || "post"}${flags ? ` [${flags}]` : ""}. Source: X, read-only.`;
    }
    if (!posts.length) {
      return `X signal (${asOf}): Quiet on X this week for matched candidate accounts. Source: X, read-only.`;
    }
    return `X signal (${asOf}): ${posts.length} candidate post(s); no attack/ad/endorsement/spike flags this window. Source: X, read-only.`;
  };

  function renderMetrics(m) {
    if (!m) return "";
    const parts = [];
    if (m.impressions != null) parts.push(`${m.impressions.toLocaleString("en-US")} imp`);
    if (m.likes != null) parts.push(`${m.likes} likes`);
    if (m.reposts != null) parts.push(`${m.reposts} reposts`);
    if (m.replies != null) parts.push(`${m.replies} replies`);
    return parts.join(" · ");
  }

  function renderPostCard(post, opts) {
    opts = opts || {};
    const id = post.id || Math.random().toString(36).slice(2);
    const flags = (post.flags || [])
      .map((f) => `<span class="chip chip-social-flag chip-flag-${f}">${escapeHtml(FLAG_LABELS[f] || f)}</span>`)
      .join("");
    const party = post.party ? `<span class="chip chip-party-${post.party.toLowerCase()}">${escapeHtml(post.party)}</span>` : "";
    const metrics = renderMetrics(post.metrics);
    const fullText = escapeHtml(post.text || "");
    const summary = escapeHtml(post.summary || post.text || "");
    const expandable = post.text && post.summary && post.text !== post.summary;
    return `
      <article class="social-post-card" data-post-id="${escapeHtml(id)}">
        <header class="social-post-head">
          <div class="social-post-who">
            <span class="social-handle">@${escapeHtml(post.handle || "—")}</span>
            <span class="social-candidate">${escapeHtml(post.candidate || "—")}</span>
            ${party}
          </div>
          <time class="social-post-time" datetime="${escapeHtml(post.created_at || "")}">${escapeHtml(relativeTime(post.created_at))}</time>
        </header>
        <p class="social-post-summary">${summary}</p>
        ${
          expandable
            ? `<details class="social-post-details"><summary>Full post text</summary><p class="social-post-full">${fullText}</p></details>`
            : fullText && !post.summary
              ? `<p class="social-post-full social-post-full-inline">${fullText}</p>`
              : ""
        }
        ${sentimentChip(post) ? `<div class="social-post-sentiment">${sentimentChip(post)}</div>` : ""}
        ${flags ? `<div class="social-post-flags">${flags}</div>` : ""}
        ${metrics ? `<p class="social-post-metrics">${escapeHtml(metrics)}</p>` : ""}
        ${
          post.url
            ? `<a class="social-open-x" href="${escapeHtml(post.url)}" target="_blank" rel="noopener noreferrer">Open on X</a>`
            : ""
        }
        ${post.author_note && opts.showAuthorNote ? `<p class="social-author-note">${escapeHtml(post.author_note)}</p>` : ""}
      </article>`;
  }

  function bindSocialPanel(root, districtId) {
    if (!root) return;
    const block = districtBlock(districtId);
    const posts = (block && block.posts) || [];
    const filterBar = root.querySelector(".social-flag-filter");
    const listEl = root.querySelector(".social-post-list");
    if (!filterBar || !listEl) return;

    function renderList(activeFlag) {
      let filtered = posts.slice();
      if (activeFlag && activeFlag !== "all") {
        filtered = filtered.filter((p) => (p.flags || []).includes(activeFlag));
      }
      filtered.sort((a, b) => {
        const da = parsePostDate(a.created_at);
        const db = parsePostDate(b.created_at);
        return (db ? db.getTime() : 0) - (da ? da.getTime() : 0);
      });
      if (!filtered.length) {
        listEl.innerHTML = `<div class="empty-state social-empty"><h3>No posts</h3><p>No candidate posts match this filter in the current ${AE.socialData.window_days || 7}-day window.</p></div>`;
        return;
      }
      listEl.innerHTML = filtered.map((p) => renderPostCard(p)).join("");
    }

    filterBar.querySelectorAll("[data-social-flag]").forEach((btn) => {
      btn.addEventListener("click", () => {
        filterBar.querySelectorAll("[data-social-flag]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        renderList(btn.getAttribute("data-social-flag"));
      });
    });
    renderList("all");
  }

  AE.social.renderPanel = function (districtId) {
    if (AE.socialLoadError) {
      return `<div class="empty-state"><h3>Social feed unavailable</h3><p>${escapeHtml(AE.socialLoadError)}</p></div>`;
    }
    if (!AE.socialData) {
      return `<div class="empty-state"><h3>Social</h3><p>Loading X digest…</p></div>`;
    }
    const code = districtIdToCode(districtId);
    const block = districtBlock(districtId);
    const posts = (block && block.posts) || [];
    const highlights = (block && block.highlights) || [];
    const noX = (block && block.no_x_presence) || [];
    const sourceChip =
      AE.socialMeta && AE.socialMeta.source === "d1"
        ? `<span class="chip chip-live">D1 LIVE</span>`
        : `<span class="chip chip-live">SEED</span>`;
    const asOf = formatAsOf(AE.socialData.as_of);
    const mentions = (AE.socialData.mentions || []).filter((m) => m.district === code);

    const highlightHtml = highlights.length
      ? `<ul class="social-highlights">${highlights.map((h) => `<li>${escapeHtml(h)}</li>`).join("")}</ul>`
      : `<p class="social-muted">No district highlights for this pull.</p>`;

    const noXHtml = noX.length
      ? `<p class="social-no-x"><strong>No X presence (verified watch list):</strong> ${noX.map((n) => escapeHtml(n)).join("; ")}</p>`
      : "";

    const flagButtons = ['all', ...FLAG_ORDER]
      .map((f) => {
        const label = f === "all" ? "All" : FLAG_LABELS[f] || f;
        return `<button type="button" class="btn btn-ghost btn-sm social-flag-btn${f === "all" ? " active" : ""}" data-social-flag="${f}">${label}</button>`;
      })
      .join("");

    const mentionsHtml = mentions.length
      ? `<section class="social-mentions" aria-label="Mentions unverified">
          <h4 class="social-subtitle">Mentions (unverified)</h4>
          <p class="social-muted">Third-party posts naming candidates — not from candidate accounts.</p>
          <div class="social-mention-list">${mentions.map((m) => renderPostCard(m, { showAuthorNote: true })).join("")}</div>
        </section>`
      : "";

    return `
      <div class="social-panel" data-district="${escapeHtml(districtId)}">
        <div class="social-panel-meta">
          ${sourceChip}
          <span class="social-as-of">As of <strong>${escapeHtml(asOf)}</strong></span>
          <span class="social-attrib">Source: X, read-only</span>
        </div>
        ${renderSentimentChartSection(districtId)}
        <section class="social-highlights-wrap">
          <h4 class="social-subtitle">District highlights</h4>
          ${highlightHtml}
        </section>
        ${noXHtml}
        <div class="social-flag-filter" role="group" aria-label="Filter posts by flag">${flagButtons}</div>
        <div class="social-post-list"></div>
        ${mentionsHtml}
      </div>`;
  };

  AE.social.bindPanel = function (districtId) {
    const wrap = document.querySelector("#social-panel");
    if (!wrap) return;
    const panel = wrap.querySelector(".social-panel");
    if (panel) bindSocialPanel(panel, districtId);
  };

  /** Candidate posts + optional flag for Ask layer */
  AE.social.queryPosts = function (opts) {
    opts = opts || {};
    const districtId = opts.districtId;
    const flag = opts.flagFilter || null;
    const candidateNeedle = opts.candidateName ? String(opts.candidateName).toLowerCase() : null;
    const code = districtIdToCode(districtId);
    const block = districtBlock(districtId);
    let posts = (block && block.posts ? block.posts.slice() : []).map((p) => ({ ...p, _kind: "candidate" }));
    if (candidateNeedle) {
      posts = posts.filter((p) => (p.candidate || "").toLowerCase().includes(candidateNeedle));
    }
    if (flag) {
      posts = posts.filter((p) => (p.flags || []).includes(flag));
    }
    let mentions = [];
    if (flag === "attack" && code && AE.socialData && AE.socialData.mentions) {
      mentions = AE.socialData.mentions
        .filter((m) => m.district === code && (m.flags || []).includes("attack"))
        .map((m) => ({ ...m, _kind: "mention" }));
    }
    posts.sort((a, b) => {
      const da = parsePostDate(a.created_at);
      const db = parsePostDate(b.created_at);
      return (db ? db.getTime() : 0) - (da ? da.getTime() : 0);
    });
    return { posts, mentions, block, code };
  };

  AE.social.load = function () {
    AE.socialData = null;
    AE.socialMeta = null;
    AE.socialLoadError = null;
    const seedUrl = "data/social/latest/social-feed.json";
    const apiUrl = apiBase() + "/api/social-feed";

    function applyPayload(json, meta) {
      AE.socialData = json.feed || json;
      AE.socialMeta = meta || { source: json.source || "api", as_of: AE.socialData.as_of };
    }

    return fetch(apiUrl, { credentials: "same-origin", cache: "no-store" })
      .then((res) => {
        if (res.ok) return res.json().then((json) => {
          if (!json.ok && !json.feed) throw new Error(json.message || "bad payload");
          applyPayload(json, {
            source: json.source,
            as_of: json.as_of,
            updated_at: json.updated_at,
            byte_size: json.byte_size,
          });
        });
        if (res.status === 401) throw new Error("session required");
        throw new Error("HTTP " + res.status);
      })
      .catch((err) => {
        return fetch(seedUrl, { cache: "no-store" })
          .then((res) => {
            if (!res.ok) throw new Error("HTTP " + res.status);
            return res.json();
          })
          .then((json) => {
            applyPayload({ feed: json }, { source: "bundle", as_of: json.as_of });
            if (err && String(err.message).indexOf("session") < 0) {
              AE.socialLoadError = null;
            }
          })
          .catch((err2) => {
            AE.socialLoadError = err2.message || String(err2);
          });
      });
  };
})();
