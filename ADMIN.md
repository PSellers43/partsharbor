# PartsHarbor admin portal

Secure, server-side admin authentication for PartsHarbor operations. The public marketing site under `docs/` stays on **GitHub Pages** (static only). This portal is a small **Node.js** service you run separately—GitHub Pages cannot host real sessions or password verification.

## Architecture

| Surface | Hosting | Auth |
|--------|---------|------|
| Public site (`partsharbor.biz`) | GitHub Pages → `docs/` | None |
| Admin (`/admin/login`, `/admin`) | Node app in `admin-portal/` | Server-side SQLite sessions + Argon2id |

**Recommended production URL:** `https://admin.partsharbor.biz` (DNS A/AAAA or CNAME to your host). The app serves routes at `/admin/login` and `/admin` on whatever origin you bind. Keeping admin on its own subdomain avoids mixing cookies with the static site and simplifies TLS + CSP.

## Security controls (implemented)

- **Passwords:** Argon2id via the `argon2` package; only hashes stored in SQLite (`admin-portal/data/admin-portal.db`, gitignored).
- **Sessions:** Stored server-side in SQLite; cookie is `HttpOnly`, `Secure` in production, `SameSite=Strict`, rolling max-age (default 8h). Production cookie names use the `__Host-` prefix (requires HTTPS and `Path=/`).
- **CSRF:** `csrf-csrf` double-submit cookie on `POST /admin/login` and `POST /admin/logout`.
- **Brute force:** IP rate limit (express-rate-limit) plus per-account failed-attempt counter and temporary lockout in SQLite.
- **User enumeration:** Single generic message for bad credentials; unknown usernames still run Argon2 verify against a dummy hash.
- **Headers:** Helmet (CSP, frame-ancestors / X-Frame-Options, HSTS in production, Referrer-Policy, etc.).
- **Logout:** `session.destroy()` removes the server-side session and clears session + CSRF cookies.
- **Secrets:** `SESSION_SECRET` from environment only—never commit `.env` or the SQLite DB.

### SameSite=Strict

Login is same-site form POST to the admin origin, so **Strict** is appropriate and is what we set. If you later add cross-site OAuth to this app, you may need `Lax` for the OAuth callback leg only—document that change explicitly.

### HSTS

HSTS is sent when `NODE_ENV=production`. Terminate TLS at your platform (Fly, Render, nginx, Cloudflare). After you confirm HTTPS works everywhere on the admin host, consider enabling HSTS preload at the registrar/CDN level.

## Local development

```bash
cd admin-portal
cp .env.example .env
# Edit .env: set SESSION_SECRET (32+ chars), e.g. openssl rand -base64 48

npm install
npm run bootstrap-admin   # interactive password, or ADMIN_BOOTSTRAP_PASSWORD for CI
npm run dev
```

Open http://127.0.0.1:8787/admin/login

**Test flow**

1. Sign in with the bootstrapped username (default `admin`, override with `ADMIN_USERNAME` at bootstrap).
2. Confirm dashboard shows username and masked session id.
3. Log out → should return to login; back button to dashboard should require login again.

## Bootstrap (first admin)

Run **once** on each new environment (laptop, staging, production):

```bash
cd admin-portal
npm run bootstrap-admin
```

- Refuses to run if an admin row already exists (no silent overwrite).
- Password min length 12 characters.
- Non-interactive (automation): set `ADMIN_BOOTSTRAP_PASSWORD` and optionally `ADMIN_USERNAME` for that single run only—do not leave the password in persistent env on the server.

To rotate password today: add a small SQL migration or re-run bootstrap on a fresh DB (document your ops process; a dedicated `rotate-admin-password` script can be added later).

## Environment variables

See `admin-portal/.env.example`. Required for production:

| Variable | Purpose |
|----------|---------|
| `SESSION_SECRET` | Session signing + CSRF secret (≥32 chars) |
| `NODE_ENV=production` | Secure cookies, HSTS, `__Host-` cookie names |
| `TRUST_PROXY=1` | Correct client IP behind Fly/Render/nginx |

Optional: `HOST`, `PORT`, `ADMIN_DATA_DIR`, `SESSION_MAX_AGE_SEC`, `ADMIN_USERNAME` (bootstrap only).

## Deploy options (pick one)

GitHub Pages **cannot** run this app. Choose a host that runs Node 20+ with persistent disk (or attached volume) for SQLite:

1. **Fly.io / Render / Railway** — run `npm start` from `admin-portal/`, set secrets in the dashboard, mount a volume at `admin-portal/data` if the platform has ephemeral filesystem.
2. **VPS + systemd + nginx** — reverse proxy to `127.0.0.1:8787`, TLS via Certbot.
3. **Cloudflare Tunnel** — expose the admin process without opening inbound ports; still use TLS on the public hostname.

Example `Dockerfile` is included in `admin-portal/Dockerfile` for container hosts.

After deploy:

1. Set `SESSION_SECRET` and `NODE_ENV=production`, `TRUST_PROXY=1`.
2. Run bootstrap **on that environment** (SSH or one-off release command)—do not copy production `admin-portal.db` from your laptop unless you intend to clone credentials.
3. Point `admin.partsharbor.biz` (or your chosen host) at the service.
4. Verify `/healthz` returns `ok`, then complete login → logout manually.

## What we explicitly did not do

- No client-only “fake” login on GitHub Pages.
- No default password in the repository.
- No AssemblyEdge or other tools wired in this shell (future routes can sit behind `requireAuth` in `src/server.js`).

## Threat model (short)

Protects against casual credential stuffing, CSRF on admin forms, session theft via non-HttpOnly cookies, and clickjacking. Does **not** replace MFA, hardware keys, or enterprise IdP—add those when ops scale. Keep the admin URL non-obfuscated but unlinked from the public site; security relies on strong passwords, rate limits, and TLS—not obscurity.
