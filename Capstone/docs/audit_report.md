# Phase 1 Application Audit Report
## Authentication, UI Consistency, Navigation & CSRF Hardening Overhaul

**Target Application:** EZ Charge Network Portal (Independent Academic Demonstration — Tata Power EZ Charge Reference)  
**Audit Scope:** `app/__init__.py`, `app/routes/`, `app/services/`, `app/db.py`, `app/templates/`, `app/static/css/style.css`, `app/static/js/`, `database/01_schema.sql`, `requirements.txt`, `.env.example`, `.gitignore`, `run.py`, `vercel.json`.

---

## 1. Executive Inventory

1. **Registered Blueprints (`app/__init__.py`):**
   - `public_bp` (`/`): Landing, About, Data Sources, Stations, Station Detail, QR scan, Privacy, Terms, Contact, Profile.
   - `auth_bp` (`/`): `/login`, `/register`, `/logout`.
   - `admin_bp` (`/admin`): Dashboard, Stations, Points, Bookings, Sessions, Payments, Users, Enquiries, Audit Logs, System Health, Data Sources, Reports, Station QR generation/print.
   - `owner_bp` (`/owner`): Dashboard, Vehicles, Stations, Book Slot, Bookings, Charging Session, Checkout, History, Receipt.
   - `api_bp` (`/api`): Point statuses, active session, session complete, slot overlap check, Razorpay order/verify/sandbox/QR/webhook, health check.
2. **Authentication & Registration (`app/routes/auth.py`, `app/services/auth_service.py`):**
   - Password-based local auth using Werkzeug `generate_password_hash` / `check_password_hash`.
   - Registration hard-codes `OWNER` role (`allow_admin=False`) — secure privilege lock, **no Google OAuth / OIDC yet**, no password visibility toggle, and no Forgot/Reset Password flow.
3. **Database Schema (`database/01_schema.sql`):**
   - `Users` table has `user_id`, `full_name`, `email (UNIQUE)`, `phone`, `password_hash (NOT NULL)`, `role ENUM('ADMIN','OWNER')`, `account_status ENUM('ACTIVE','INACTIVE')`, `created_at`.
   - Missing OAuth/OIDC & lifecycle columns: `google_sub`, `auth_provider`, `email_verified`, `profile_picture_url`, `updated_at`, `last_login`, nullable `password_hash`, and `PasswordResetTokens`.
4. **Session & CSRF Protection (`app/__init__.py`, `app/routes/auth_middleware.py`, `app/static/js/main.js`):**
   - `Flask-WTF` `CSRFProtect` initialized globally (`WTF_CSRF_TIME_LIMIT = 3600`), `SESSION_COOKIE_HTTPONLY = True`, `SameSite = "Lax"`, `SESSION_COOKIE_SECURE` tied to production/Vercel env.
   - `_verify_active_session_user()` checks DB `account_status == 'ACTIVE'` and syncs `session["role"]`.
   - `@csrf.exempt` applied **only** to `POST /api/payments/razorpay/webhook` (authenticated via `X-Razorpay-Signature` HMAC).
5. **Layouts, Theme Split & Sidebar Navigation (`app/templates/base.html`, `app/static/css/style.css`, `app/static/js/main.js`):**
   - Public pages, Auth pages, and Owner portal use Deep Midnight Navy (`#0B1220` / `#111C2E` / `#00C985` / `#00D4FF`).
   - **Theme Conflict:** `style.css` lines 1472–1799 override `body.has-admin-sidebar` with a bright white/slate Light Theme (`#F4F7FA` / `#FFFFFF`), plus hardcoded `#475569` / `#64748B` / `#E2E8F0` / `#059669` / `#D97706` in `admin/dashboard.html`, `admin/data_sources.html`, `admin/stations.html`, and `data_sources.html`.

---

## 2. Root-Cause Findings

### Finding 1 — `"400 Security check failed (invalid or missing CSRF token)"`
1. **Browser `bfcache` & Stale Form Tokens:** When a user logs in, logs out, navigates back (`history.back()`), or leaves a form tab open across a login (`session.clear()` in `auth.py`), the previously rendered HTML still holds a stale `<input name="csrf_token">` and `<meta name="csrf-token">`. Submitting it triggers `CSRFError` (400).
2. **Session Expiration Recovery:** Once `WTF_CSRF_TIME_LIMIT` expires or cookies clear, `CSRFError` currently renders generic `error.html` without offering automatic token refresh (`GET /auth/csrf-token` on `pageshow`/retry) or an explicit reload/re-login recovery prompt.

### Finding 2 — Admin Sidebar Navigation Flicker & Layout Shift
1. **Post-Paint Collapsed Class (`main.js`):** `base.html` paints `<body class="has-admin-sidebar">` initially at full sidebar width (`260px`), and only *after* parsing the bottom of `<body>` does `DOMContentLoaded` in `main.js` read `localStorage('ev_sidebar_collapsed')` and add `.sidebar-collapsed` (`76px`). Every navigation flashes expanded -> collapsed and shifts `.admin-workspace` width.
2. **Initial Transition Replay & Hover Transitions:** CSS `transition: width 0.2s ease` / `margin-left 0.2s ease` triggers on initial paint when `.sidebar-collapsed` is toggled synchronously or asynchronously unless disabled on first frame (`no-sidebar-transition` cleared after `requestAnimationFrame`), and `--transition: all 0.18s ...` on `.sidebar-link` triggers overly broad `all`-property repaints.
3. **Dark/Light Flash on Route Switch:** Switching between Public/Profile routes (`#0B1220`) and Admin routes (`#F4F7FA`) causes stark background luminance flashing.

### Finding 3 — Missing Google OAuth 2.0 & Auth UX Gaps
- `Authlib` is absent from `requirements.txt`; no `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` config exists; `/login` and `/register` lack Google Sign-In, password visibility toggles, and Forgot/Reset Password flows.

---

## 3. Remediation Plan
1. Apply MySQL migration `007_google_oauth_and_auth_overhaul.sql` extending `Users` safely + adding `PasswordResetTokens`.
2. Integrate `Authlib` OIDC Google Sign-In (`/auth/google/login`, `/auth/google/callback`) with state/nonce checks, strict verified-email checks, safe linking, non-ADMIN role lock, graceful unconfigured fallback, plus `/forgot-password` and `/reset-password/<token>`.
3. Add `/auth/csrf-token` refresh endpoint + `pageshow` (`bfcache`) & AJAX retry token sync + friendly `CSRFError` recovery UX.
4. Unify all interfaces under one cohesive Dark EV theme (`#0B1220` / `#111C2E` / `#162338` / `#00D6A0` / `#00C8FF` / `#F8FAFC` / `#94A3B8` / `#26364C`), removing the Light Admin override and fixing Chart.js + template contrast.
5. Eliminate sidebar FOUC & flicker with synchronous `<head>` state initialization (`html.sidebar-collapsed` + `html.sidebar-no-anim`) and restrained GPU-friendly transitions.
