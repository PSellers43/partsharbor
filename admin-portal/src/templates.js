function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function layout(title, body) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <meta name="theme-color" content="#0c1222">
  <title>${esc(title)} · PartsHarbor Admin</title>
  <link rel="stylesheet" href="/admin/static/admin.css">
</head>
<body>
${body}
<p class="footer-note">PartsHarbor internal admin · Authorized use only</p>
</body>
</html>`;
}

export function renderLogin({ title, error, next, csrfToken }) {
  const errBlock = error
    ? `<div class="alert alert-error" role="alert">${esc(error)}</div>`
    : "";
  const nextField = next ? `<input type="hidden" name="next" value="${esc(next)}">` : "";
  return layout(
    title,
    `<header class="admin-header">
  <div class="brand">PartsHarbor <span>Admin</span></div>
</header>
<main class="admin-main">
  <div class="card">
    <h1>Sign in</h1>
    <p class="subtitle">Operations and admin access for PartsHarbor.</p>
    ${errBlock}
    <form method="post" action="/admin/login" autocomplete="off">
      <input type="hidden" name="_csrf" value="${esc(csrfToken)}">
      ${nextField}
      <div class="field">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" required autocapitalize="none" autocomplete="username" maxlength="64">
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" required autocomplete="current-password" maxlength="256">
      </div>
      <button type="submit" class="btn btn-primary">Sign in</button>
    </form>
  </div>
</main>`,
  );
}

export function renderDashboard({ title, csrfToken, sessionMeta }) {
  const expiresRow = sessionMeta.expires
    ? `<li><span class="label">Cookie expires (UTC)</span><span>${esc(new Date(sessionMeta.expires).toISOString())}</span></li>`
    : "";
  return layout(
    title,
    `<header class="admin-header">
  <div class="brand">PartsHarbor <span>Admin</span></div>
  <form method="post" action="/admin/logout">
    <input type="hidden" name="_csrf" value="${esc(csrfToken)}">
    <button type="submit" class="btn btn-ghost">Log out</button>
  </form>
</header>
<main class="admin-main">
  <div class="card">
    <h1>Welcome</h1>
    <p class="subtitle">You are signed in to the PartsHarbor admin portal. Internal tools use the same session cookie—no second sign-in.</p>
    <div class="tool-links">
      <a class="btn btn-primary" href="/admin/assemblyedge/">Open AssemblyEdge</a>
      <p class="tool-links-note">Analyst + Campaign Manager prototype (Today&apos;s Board, money / CAL-ACCESS panels).</p>
    </div>
    <ul class="meta-list">
      <li><span class="label">Signed in as</span><span>${esc(sessionMeta.username)}</span></li>
      <li><span class="label">Session</span><span>${esc(sessionMeta.sessionId)}</span></li>
      ${expiresRow}
    </ul>
  </div>
</main>`,
  );
}

export function renderError({ title, message, status }) {
  return layout(
    title,
    `<header class="admin-header">
  <div class="brand">PartsHarbor <span>Admin</span></div>
</header>
<main class="admin-main">
  <div class="card">
    <h1>${esc(status)} — ${esc(title)}</h1>
    <p class="subtitle">${esc(message)}</p>
    <p><a href="/admin/login">Return to sign in</a></p>
  </div>
</main>`,
  );
}

export function htmlResponse(html, status = 200, extraHeaders = {}) {
  const headers = new Headers({
    "Content-Type": "text/html; charset=utf-8",
    ...extraHeaders,
  });
  return new Response(html, { status, headers });
}
