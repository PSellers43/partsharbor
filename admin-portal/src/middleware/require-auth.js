export function requireAuth(req, res, next) {
  if (req.session?.admin?.id) {
    return next();
  }
  const nextUrl = encodeURIComponent(req.originalUrl || "/admin");
  return res.redirect(`/admin/login?next=${nextUrl}`);
}

export function redirectIfAuthed(req, res, next) {
  if (req.session?.admin?.id) {
    const next = safeNextPath(req.query.next);
    return res.redirect(next || "/admin");
  }
  return next();
}

export function safeNextPath(raw) {
  if (typeof raw !== "string" || !raw.startsWith("/admin") || raw.startsWith("//")) {
    return null;
  }
  return raw;
}
