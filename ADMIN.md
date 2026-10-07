# PartsHarbor admin portal

Secure, server-side admin authentication for PartsHarbor operations. The public marketing site under `docs/` stays on **GitHub Pages** (static only). The admin portal is a **Cloudflare Worker** with **D1** (SQLite) for sessions and credentials.

## Architecture

| Surface | Hosting | Auth |
|--------|---------|------|
| Public site (`partsharbor.biz`) | GitHub Pages → `docs/` | None |
| Admin (`/admin/login`, `/admin`) | Cloudflare Worker + D1 | Server-side sessions + Argon2id |

**Production URL:** `https://admin.partsharbor.biz` (Cloudflare custom domain on the Worker) or `*.workers.dev` until DNS is attached.

The Express + local SQLite stack from the initial portal PR has been **removed**; this Worker is the only supported runtime.

## Security controls (implemented)

- **Passwords:** Argon2id PHC strings in D1. Runtime hashing uses the [`argon2id`](https://www.npmjs.com/package/argon2id) Wasm module (OpenPGP.js build). Bootstrap uses the Node [`argon2`](https://www.npmjs.com/package/argon2) package with identical parameters—see `scripts/cross-verify-argon.mjs`.
- **Sessions:** Stored in D1; cookie `HttpOnly`, `Secure` in production, `SameSite=Strict`, rolling max-age (default 8h). Production uses `__Host-` cookie names.
- **CSRF:** Double-submit cookie on `POST /admin/login` and `POST /admin/logout`.
- **Brute force:** IP attempt logging + per-account lockout in D1 (same thresholds as the original portal).
- **User enumeration:** Generic invalid-credentials message; unknown usernames still verify against a fixed dummy Argon2 hash.
- **Headers:** CSP, `X-Frame-Options`, HSTS in production, `Referrer-Policy`, `no-store` caching.
- **Logout:** Deletes D1 session row and clears cookies.
- **Secrets:** `SESSION_SECRET` via Wrangler secret / `.dev.vars` only.

### Argon2 on Workers (read this)

Cloudflare **Workers Free** enforces about **10 ms CPU time per HTTP request** (see [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)). Argon2id is deliberately slow; even with Wasm, login may exceed 10 ms CPU and return **1102 / exceeded CPU** on Free.

| Tier | Recommendation |
|------|----------------|
| **Workers Free ($0)** | Default params in `wrangler.toml`: `m=8192`, `t=2`, `p=1`. May work intermittently; monitor Metrics → **Exceeded CPU**. If login fails after deploy, reduce `ARGON2_PASSES` to `1` via Vars or upgrade. |
| **Workers Paid** | Safer for admin login; you can raise `cpu_ms` and use stronger Argon2 settings. |

We do **not** downgrade to PBKDF2 on the Worker while keeping the same security story—Argon2id stays the algorithm; you tune params or plan tier for CPU headroom.

### SameSite=Strict

Same-site form POST to the admin origin; **Strict** is correct. Revisit only if you add cross-site OAuth.

## Local development (`wrangler dev`)

```bash
cd admin-portal
cp .dev.vars.example .dev.vars
# Set SESSION_SECRET (≥32 chars), e.g. openssl rand -base64 48

npm install
npm run db:migrate:local
npm run bootstrap-admin          # local D1 only; uses --file insert (PHC $ chars safe)
npm run dev                      # http://localhost:8787
```

**Test flow**

1. Open http://localhost:8787/admin/login  
2. Sign in (default user `admin` after bootstrap)  
3. Dashboard → logout → login again  

`wrangler dev` uses a **local** D1 database under `.wrangler/` (not committed). Re-run bootstrap after wiping local state.

## Bootstrap (first admin)

**Local D1**

```bash
cd admin-portal
npm run db:migrate:local
npm run bootstrap-admin
```

**Production D1** (after remote migrations)

```bash
npm run db:migrate:remote
ADMIN_BOOTSTRAP_PASSWORD='…' npm run bootstrap-admin:remote
```

- Refuses to run if an admin row already exists.  
- Password minimum 12 characters.  
- Use `ADMIN_USERNAME` optionally for the first user.  
- Never commit `.dev.vars`, bootstrap passwords, or production D1 dumps.

## Cloudflare deploy (free account)

### One-time setup

1. Install Wrangler and log in: `npx wrangler login`
2. Create D1 database:
   ```bash
   cd admin-portal
   npx wrangler d1 create partsharbor-admin
   ```
3. Copy the returned `database_id` into `admin-portal/wrangler.toml` under `[[d1_databases]]`.
4. Apply migrations remotely:
   ```bash
   npm run db:migrate:remote
   ```
5. Set secrets and production flag:
   ```bash
   npx wrangler secret put SESSION_SECRET
   # paste ≥32 random bytes
   ```
   In the Cloudflare dashboard (or `wrangler.toml` `[vars]`), set `ENVIRONMENT=production` for Secure cookies and HSTS.

6. Bootstrap the **remote** admin (once):
   ```bash
   ADMIN_BOOTSTRAP_PASSWORD='…' npm run bootstrap-admin:remote
   ```

7. Deploy:
   ```bash
   npm run deploy
   ```

8. Smoke test: `GET https://<your-worker>/healthz` → `ok`, then login → logout in the browser.

### Custom domain (`admin.partsharbor.biz`)

1. Workers & Pages → your Worker → **Settings → Domains & Routes** → **Add Custom Domain** → `admin.partsharbor.biz`.
2. Cloudflare DNS (zone for `partsharbor.biz`) must be on Cloudflare; the UI adds the required records.
3. Confirm HTTPS and `ENVIRONMENT=production`, then repeat login/logout.

Until DNS is ready, use the `*.workers.dev` URL from `wrangler deploy`.

### Wrangler variables (non-secret)

| Name | Purpose |
|------|---------|
| `ENVIRONMENT` | `production` → Secure cookies, HSTS, `__Host-` names |
| `ARGON2_MEMORY_KIB` | Argon2 memory (KiB), default `8192` |
| `ARGON2_PASSES` | Argon2 time cost, default `2` |
| `ARGON2_PARALLELISM` | Default `1` |
| `SESSION_MAX_AGE_SEC` | Session cookie lifetime, default `28800` (8h) |

## What we did not do

- No client-only auth on GitHub Pages.  
- No default password in the repo.  
- No AssemblyEdge tools in this shell.

## Threat model (short)

Protects against casual credential stuffing, CSRF on admin forms, session theft via non-HttpOnly cookies, and clickjacking. Does **not** replace MFA or enterprise IdP. Relies on strong passwords, rate limits, TLS, and Cloudflare edge protections—not URL secrecy.
