# Google OAuth 2.0 / OIDC Setup, CSRF & UI Unification Guide

## 1. Authentication Architecture
The **EZ Charge Network Portal** supports dual-mode server-side authentication on Flask + MySQL 8.0+:
1. **Local Email & Password** (`POST /login`, `POST /register`, `/forgot-password`, `/reset-password/<token>`) backed by Werkzeug password hashing and `PasswordResetTokens`.
2. **Google OAuth 2.0 / OpenID Connect** (`GET /auth/google/login`, `GET /auth/google/callback`, `GET /auth/google/link`) via `Authlib`.

---

## 2. OAuth Authorization Code Flow & Security Protections
1. User clicks **Continue with Google** (`/auth/google/login`).
2. Flask checks `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. If missing, it redirects safely back to `/login` with a setup notice.
3. Flask generates a CSPRNG `nonce` stored in the signed HTTP-only session alongside Authlib's OAuth `state` parameter (protecting against OAuth CSRF/login-CSRF), and redirects to Google OIDC authorization URL (`scope="openid email profile"`).
4. On `/auth/google/callback`, Authlib exchanges the authorization `code`, validates `state` and `nonce`, and verifies the ID token signature & claims.
5. **Email Verification Enforcement**: Logins with `email_verified != True` are rejected cleanly.
6. **Privilege Boundary Enforcement**: Newly registered Google users always receive role `OWNER` (never `ADMIN`). Admin roles must be explicitly provisioned by an existing authenticated administrator.
7. **Safe Account Linking Policy**:
   - Matching `google_sub` signs into the linked active account and updates `last_login`.
   - Matching `email` on an already verified account (or Google-only account) links `google_sub` and upgrades `auth_provider` to `HYBRID` or `GOOGLE`.
   - Matching `email` on an **unverified local password account** (`password_hash IS NOT NULL` and `email_verified = 0`) is **blocked from automatic linking** to prevent account takeover; the user is instructed to sign in with their password first and click **Link Verified Google Account** in `/profile` (`/auth/google/link`).

---

## 3. Database Schema & Migration (`007_google_oauth_and_auth_overhaul.sql`)
Run `python init_db.py --mode migrate` to apply idempotent upgrades safely:
- `Users.password_hash`: modified to nullable (`VARCHAR(255) NULL`) for passwordless Google OAuth users.
- `Users.role`: `ENUM('ADMIN', 'OWNER', 'USER') NOT NULL DEFAULT 'OWNER'`.
- `Users.google_sub`: `VARCHAR(255) NULL UNIQUE` (Google immutable subject ID).
- `Users.auth_provider`: `ENUM('LOCAL', 'GOOGLE', 'HYBRID') NOT NULL DEFAULT 'LOCAL'`.
- `Users.email_verified`: `TINYINT(1) NOT NULL DEFAULT 0`.
- `Users.profile_picture_url`, `updated_at`, `last_login`.
- `PasswordResetTokens`: timed single-use SHA-256 hashed tokens (`expires_at`, `used_at`).

---

## 4. Environment Variables (`.env.example`)
```ini
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/auth/google/callback
```
> Keep `GOOGLE_CLIENT_SECRET` strictly in server environment variables (never in templates, JS, or `.git`).

---

## 5. Google Cloud Console Setup Checklist (Local & Vercel)
1. Open Google Cloud Console -> **APIs & Services -> OAuth consent screen**.
2. Choose **External** (or Internal for Workspace), enter App Name (`EZ Charge Network Portal`), Support Email, and Authorized Domains.
3. Add non-sensitive scopes: `openid`, `email`, `profile`.
4. Go to **Credentials -> Create Credentials -> OAuth client ID** -> **Web application**.
5. Add **Authorized JavaScript origins**:
   - Local: `http://127.0.0.1:5000`, `http://localhost:5000`
   - Production: `https://<your-app>.vercel.app`
6. Add **Authorized redirect URIs**:
   - Local: `http://127.0.0.1:5000/auth/google/callback`
   - Production: `https://<your-app>.vercel.app/auth/google/callback`
7. Copy the generated Client ID and Client Secret into `.env` locally and Vercel **Project Settings -> Environment Variables** in production (setting `GOOGLE_REDIRECT_URI=https://<your-app>.vercel.app/auth/google/callback` on Vercel).

---

## 6. Root Cause & Fix: CSRF `"400 Security check failed"`
- **Cause**: Browser back-button `bfcache` restores HTML pages containing old `<input name="csrf_token">` values generated *before* `session.clear()` on login/logout, or tabs stay open beyond `WTF_CSRF_TIME_LIMIT` (3600s).
- **Fixes Applied**:
  1. `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` on `/login`, `/register`, `/forgot-password`, `/reset-password*`, `/auth/csrf-token`.
  2. `GET /auth/csrf-token` JSON endpoint paired with `window.addEventListener('pageshow', ...)` (`bfcache` restoration) and `csrfFetch()` auto-retry in `app/static/js/main.js`.
  3. Actionable recovery UI (`error.html`) on 400 `CSRFError` with one-click `"Reload Fresh Form"` and `"Sign In Again"` links while keeping strict HTTP `400` enforcement.

---

## 7. Root Cause & Fix: Unified Dark Theme & Zero-Flicker Sidebar
- **Theme Unification**: Removed the legacy Light Admin override (`#F4F7FA` / `#FFFFFF`) in `app/static/css/style.css` and unified Public, Auth, Owner, and Admin workspaces onto Deep Midnight Navy (`#0B1220`), Dark Slate (`#111C2E` / `#162338`), Electric Emerald (`#00D6A0`), and Cyan (`#00C8FF`) plus dark-themed Chart.js defaults.
- **Sidebar Flicker Fix**: Moved collapsed sidebar detection into a synchronous `<head>` inline script in `app/templates/base.html` (`html.sidebar-is-collapsed` + `html.sidebar-preload`) so desktop layouts render collapsed on Frame 0 with initial-load CSS transitions suppressed until after first animation frame (`requestAnimationFrame`), and replaced `transition: all` on `.sidebar-link` with targeted color/background transitions plus `prefers-reduced-motion` support.

