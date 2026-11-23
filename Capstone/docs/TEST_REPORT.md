# Automated Test & Visual Verification Report

## 1. Automated Pytest Suite

Executed via `python -m pytest -v` against local **MySQL 8.0+ (`ev_charging_db`, Migration 009 applied)** on Windows + Python 3.13.

### Coverage Modules (16 Suites, 113 Tests)
1. `tests/test_audit_and_settings.py` (5 tests): API health diagnostics, audit log persistence, admin system settings CRUD.
2. `tests/test_auth.py` (6 tests): Admin & Owner authentication, invalid password rejection, registration & duplicate email protection.
3. `tests/test_booking.py` (5 tests): Slot reservation creation, DB overlap prevention (`trg_booking_before_insert`), date validation, vehicle ownership enforcement, booking cancellation.
4. `tests/test_contact_web3forms.py` (6 tests): CSRF validation, Web3Forms backend proxy forwarding, fallback persistence on HTTP failure, honeypot/rate-limit/duplicate lock, admin enquiry triage.
5. `tests/test_database_architecture.py` (7 tests): `DATABASE_URL` SSL parsing, invalid scheme rejection, `PooledDB` concurrency, graceful connection failure handling, zero-N+1 station counts, portable health check, delimiter SQL parser.
6. `tests/test_free_apis.py` (8 tests): Free HTTP client cache/retry, Open Charge Map POI ingestion & deduplication, ChargeAlong documentation notes, Nominatim geocoding & reverse geocoding, OSRM routing polyline, Open-Meteo weather forecast, India PIN Code 6-digit post office lookup, Dispenser & Booking QR token rotators and admin check-in.
7. `tests/test_oauth_csrf_and_ui.py` (6 tests): Unconfigured Google OAuth fallback notice, mocked OIDC login/callback, unverified-email rejection, safe local-account link guard against unverified password accounts, Forgot/Reset Password single-use SHA-256 token flow, `GET /auth/csrf-token` + `no-store` auth headers + 400 recovery UI, unified Dark EV theme CSS & pre-paint zero-flicker sidebar verification.
8. `tests/test_qr_and_provenance.py` (5 tests):
   - Station Identification QR lifecycle (`PNG`/`SVG`/printable placard, `/qr/station/<token>` scan count & `/station/<slug>` redirect, `/image.png` preview without incrementing scans, token regeneration revoking old token `410`, revocation blocking scans `410`, invalid token `404`, non-admin `403`).
   - Null-coordinate `PENDING_VERIFICATION` exclusion from `/api/stations/map`, `"Location verification pending."` UI rendering, Admin verification status transitions + non-admin `403`.
   - Dynamic Payment QR (`POST /api/payments/razorpay/qr`) ownership IDOR guard, `ttl_seconds = 600`, non-settlement upon generation (`PENDING`), and server-enforced `EXPIRED` rejection after TTL expiry.
   - All 8 Admin Chart.js canvases (`chartMonthlyBookings`, `chartMonthlySessions`, `chartCityStations`, `chartCapacityDist`, `chartBookingStatus`, `chartPaymentStatus`, `chartEnquiryStatus`, `chartConnectorMix`), legal routes (`/privacy`, `/terms`), and Oct 2026 Press Release homepage sections.
   - Complete `url_for()` static-template/route audit (231 references across 69 registered endpoints), Privacy Policy section completeness, and `DEBUG=False` production override.
9. `tests/test_razorpay_checkout.py` (5 tests): Strict `rzp_live_*` guardrail, checkout page IDOR protection & 18% GST invoice breakdown, server-computed order creation, forged signature rejection, sandbox HMAC verification, idempotent webhook event ingestion, Admin dashboard media & charts.
10. `tests/test_real_world_platform.py` (6 tests): Tata Power EZ Charge reference branding & verified social handles, NCR geospatial API filters, CSV import validation & approval gate, simulated payment retry & downloadable `.txt` receipts, Admin governance & Data Sources register, MySQL/Postgres dialect isolation.
11. `tests/test_saas_features.py` (13 tests): Landing page metrics, stations directory, station detail page, admin user provisioning & status toggling, system health, vehicle edit & IDOR guard, session receipts & CSV export.
12. `tests/test_security_hardening.py` (11 tests): Public registration admin-escalation block, absence of leaked credentials on `/login`, admin-only user creation, payment/session IDOR blocks, CSRF enforcement, inactive session revocation, SQL injection safety, production `SECRET_KEY` enforcement, secure cookie flags.
13. `tests/test_security_rbac.py` (6 tests): RBAC isolation between `ADMIN`, `OWNER`, `CUSTOMER` and anonymous clients, cross-user vehicle/booking IDOR rejection, atomic transaction rollback.
14. `tests/test_session_payment.py` (3 tests): `CompleteChargingSession` stored procedure & `CalculateChargingCost`, negative energy rejection, duplicate transaction reference rejection.
15. `tests/test_vercel_deployment.py` (2 tests): `vercel.json` routing validation and `api/index.py` WSGI entrypoint verification.
16. `tests/test_customer_owner_upgrade.py` (15 tests):
    - Public registration defaults to `CUSTOMER` and rejects role injection (`ADMIN`, `OWNER`).
    - Sliding window IP + email rate limiting.
    - Remember-me cookie session handling with secure flags.
    - Avatar upload MIME and magic-number validation (PNG, JPG, WebP) blocking binaries.
    - Customer dashboard KPIs strictly scoped to user's own vehicle fleet, active sessions, and bookings.
    - Vehicles CRUD with category enums (`2W`, `3W`, `4W_SUV`, `4W_SEDAN`, `FLEET_BUS`, `COMMERCIAL`), connector types, and atomic primary vehicle toggle.
    - Atomic booking slot calculation with battery SoC estimates, price estimates, and check-in QR generation.
    - Saved stations bookmarking toggle and retrieval.
    - In-app notification lifecycle (creation, unread badge count, mark as read).
    - Unified multi-type QR code resolver (`/api/qr/resolve/<token>`) supporting Dispensers (`POINT`), Station Placards (`STATION`), and Booking Check-ins (`BOOKING`).
    - Station Partner onboarding application submission (`/owner/apply`) and Admin review queue (`/admin/owner-applications`).
    - Station Partner dashboard KPIs and strict hardware IDOR isolation (`s.owner_user_id = uid`).
    - Strict 403 block preventing Customers from accessing Station Partner hardware routes.
    - Admin user detail inspection (`/admin/users/<id>`) showing profile metadata, role change, and status toggle.
    - Customer charging history with pagination, session detail receipt view, text receipt download, and CSV export.

**Latest Pytest Outcome**: **113 passed, 0 failed, 0 skipped in 12.63s (100% Green).**

---

## 2. Syntax & Live Smoke Verification

- **Python Bytecode Compile Check (`python -m compileall -q app api init_db.py run.py tests`)**: Exit code `0` (Zero syntax errors).
- **Live Smoke Verification (`scratch/verify_live.py`)**:
  - `[PASS]` 1. Landing page OK (200)
  - `[PASS]` 2. Registration page OK - purely Customer oriented, zero role escalations
  - `[PASS]` 3. Partner Onboarding Application OK (200)
  - `[PASS]` 4. Customer login redirected to Customer Portal with scoped telemetry
  - `[PASS]` 5. Customer EV Garage accessible
  - `[PASS]` 6. Customer strictly blocked from Station Partner & Admin hardware/dashboards (403)
  - `[PASS]` 7. Station Partner login OK - redirected to Partner Console (`/owner/dashboard`)
  - `[PASS]` 8. Partner Station Management OK - scoped to owned station (Connaught Place EV Hub)
  - `[PASS]` 9. Admin login OK - redirected to Admin Central Oversight (`/admin/dashboard`)
  - `[PASS]` 10. Admin User Detail Inspection OK (`/admin/users/2`)
  - `[PASS]` 11. Admin Partner Applications Queue OK (`/admin/owner-applications`)

---

## 3. Server Status
- Process: Flask WSGI server running live on `http://127.0.0.1:5000`
- MySQL 8.0: `127.0.0.1:3306` (`ev_charging_db`)
