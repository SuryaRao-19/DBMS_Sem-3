# Security Architecture & Hardening Guide

## Overview
The **EZ Charge Network Portal (EV ChargeNet)** enforces defense-in-depth across authentication, authorization, database transactions, session cookies, CSRF protection, Dual QR integrity, Razorpay Test Mode billing, and third-party API proxying.

---

## 1. Authentication, Google OAuth 2.0 & Role-Based Access Control (RBAC)

- **Public Registration & OAuth Privilege Lockdown**: `/register` strictly enforces non-admin registration (`allow_admin=False` in `app/services/auth_service.py`). Non-owner role submission returns `HTTP 403`. New **Google OAuth 2.0 / OIDC** (`/auth/google/callback`) accounts always receive `role='OWNER'` and never `ADMIN`.
- **Google OIDC State, Nonce & Safe Linking**: Authlib OIDC flows validate CSPRNG `state` and `nonce` claims plus `email_verified=True`. Existing **unverified local password accounts** are never blindly linked on email match (`UNVERIFIED LOCAL` protection against account takeover) — users must authenticate with their password first and explicitly link via `/auth/google/link`.
- **Forgot / Reset Password**: `/forgot-password` and `/reset-password/<token>` store single-use SHA-256 hashed 30-minute tokens in `PasswordResetTokens` without leaking account existence.
- **Protected Admin Provisioning**: New administrator accounts are created exclusively by authenticated `ADMIN` users (`POST /admin/users/create`) and logged in `AuditLogs`.
- **Per-Request Account Status Enforcement**: `app/routes/auth_middleware.py` checks `Users.account_status == 'ACTIVE'` on every authenticated request (`401` on API routes, session cleared + redirect on HTML routes).
- **Password Hashing**: Werkzeug `scrypt` (`generate_password_hash` / `check_password_hash`). No demo passwords appear on `login.html` or client JavaScript.

---

## 2. Insecure Direct Object Reference (IDOR) & Transaction Integrity

- **Bookings, Vehicles, Sessions, Receipts**: Every route scopes SQL queries by `session["user_id"]` and uses parameterized placeholders (`%s`).
- **Atomic Row Locking**: `start_session()` locks `ChargingPoints` and user active sessions via `SELECT ... FOR UPDATE`; completion calls stored procedure `CompleteChargingSession` + `CalculateChargingCost`.
- **Server-Computed Billing**: `create_razorpay_order()` and `create_dynamic_payment_qr()` derive totals strictly from server `ChargingSessions.total_cost` inside MySQL.

---

## 3. Dual QR & Razorpay TEST MODE Controls

- **Live Key Guardrail**: `app/services/razorpay_service.py` raises an error if `RAZORPAY_KEY_ID` begins with `rzp_live_`. Only `rzp_test_*` keys or local test sandbox tokens are accepted.
- **HMAC-SHA256 Verification & Webhook Idempotency**: All checkout settlements verify `HMAC_SHA256(order_id|payment_id, secret)` via `hmac.compare_digest`. `/api/payments/razorpay/webhook` validates `X-Razorpay-Signature`, logs `event_id` in `PaymentWebhookEvents` to drop replays, and never downgrades settled rows.
- **Opaque Station QRs**: `StationQRCodes` uses unpredictable `secrets.token_urlsafe` tokens instead of PII or guessable incremental IDs, with immediate Admin revocation (`410 Gone`).

---

## 4. CSRF, Cookies & Secret Management

- Global `CSRFProtect` (`Flask-WTF`) protects all forms and AJAX `POST` routes (`X-CSRFToken` header via `getCsrfToken()` in `main.js`). The Razorpay webhook endpoint (`/api/payments/razorpay/webhook`) is `@csrf.exempt` and cryptographically authenticated via `X-Razorpay-Signature`.
- `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `SESSION_COOKIE_SECURE = True` in production / Vercel, and `PERMANENT_SESSION_LIFETIME = 2 hours`.
- Production environments (`FLASK_ENV=production` / `VERCEL=1`) fail fast if `SECRET_KEY` is missing or matches development placeholders. `.env` is excluded via `.gitignore` and `.vercelignore`.
