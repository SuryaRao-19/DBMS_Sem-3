# EZ Charge Network Portal — Tata Power EZ Charge Reference Demo (EV ChargeNet)

> **Independent Academic Demonstration Notice:** This application is an independently developed academic demonstration built on the **EV ChargeNet** Flask + MySQL 8.0+ engine using publicly available **Tata Power EZ Charge** reference information. It is **not** an official Tata Power application and cannot control real charging hardware or process live commercial payments.

---

## Core Platform Capabilities

### 1. Public Website & Interactive Discovery (`/`, `/stations`, `/station/<slug>`, `/about`, `/data-sources`, `/contact`, `/privacy`, `/terms`)
- **Oct 12, 2026 Press Release Baseline + Historical Conflict Note (`/`)**: Displays verified Tata Power EZ Charge figures (`6,700+` charging points, `2.5 lakh+` home chargers, `1,200+` e-bus points, `7 lakh+` customers, `700+` cities) alongside source links, publication dates, and explicit scope reconciliation notes vs earlier `5,500+` / `620+` corporate disclosures.
- **Coordinate-Verified Station Directory & Interactive Map (`/stations`, `/api/stations/map`)**: Distinguishes coordinate-verified stations (including Dr. Ambedkar International Centre at 15 Janpath, plus curated NCR hubs) from press-release candidate hubs (`PENDING_VERIFICATION`, `latitude=NULL`, `longitude=NULL`) which show `"Location verification pending."` and never plot as fake map pins. Supports Google Maps JavaScript API (+ Places) with automatic zero-key Leaflet.js + OpenStreetMap fallback.
- **4 Charging Solutions & Official Ecosystem**: Home Charging, Public Charging, Workplace/Fleet Charging, and E-Bus Depot Charging, plus official Android (`com.tatapower.evapp`), Apple App Store (`id1496350476`), Linktree, and verified Tata Power social handles (`@tatapower`, `@TataPowerCompanyLtd`).
- **Web3Forms Contact & Enquiry Proxy (`/contact`)**: CSRF-protected backend proxy with input sanitization, honeypot field, DB rate limiting & deduplication, MySQL backup persistence (`ContactMessages`), and Web3Forms API delivery.

### 2. Dual QR Architecture
- **A. Station Identification QR (`StationQRCodes` + `app/services/qr_service.py`)**:
  - Static physical placard QR encoding an opaque non-PII token (`/qr/station/<token>`).
  - Public scan endpoint increments `scan_count` & `last_scanned_at` and redirects to `/station/<slug>`.
  - Admin controls (`/admin/stations`): Generate, Regenerate (auto-revoking old token -> HTTP `410 Gone`), Revoke, download high-DPI PNG, download vector SVG, and open printable signage (`/admin/stations/<id>/qr/print`).
- **B. Dynamic Payment QR & Razorpay TEST MODE (`/owner/checkout/<session_id>`, `/api/payments/razorpay/qr`)**:
  - Single-use dynamic invoice QR bound strictly to server-computed `ChargingSessions.total_cost` (including 18% GST) with a 10-minute `qr_expires_at` TTL.
  - Strict `rzp_live_*` key blocker; scanning the payment QR **never** marks a payment `SUCCESS` — settlement requires Razorpay HMAC-SHA256 verification (`/api/payments/razorpay/verify`, `/sandbox-complete`) or signed webhook delivery (`/api/payments/razorpay/webhook`).

### 3. Unified Dark EV UI, Google OAuth 2.0 & Role-Separated Dashboards (`/admin/*`, `/owner/*`, `/login`, `/register`)
- **Unified Deep Midnight Navy Design System**: Consistent dark EV theme (`#0B1220` / `#111C2E` / `#162338` / `#00D6A0` / `#00C8FF`) across Public views, Auth pages, EV Owner Console, and Admin Workspace, with synchronous pre-paint collapsed sidebar state eliminating navigation flicker.
- **Server-Side Google OAuth 2.0 / OIDC + Local Auth**: Authlib Google Sign-In (`/auth/google/login`, `/auth/google/callback`) with `state` + `nonce` validation, safe account linking, password visibility toggles, `/forgot-password` timed token reset, and `bfcache` CSRF token refresh (`GET /auth/csrf-token`). See [`docs/GOOGLE_OAUTH_SETUP.md`](./docs/GOOGLE_OAUTH_SETUP.md).
- **Admin Governance & 8 Chart.js Analytics (`/admin/dashboard`)**: Strictly separates Type A Official Reference metrics, Type B Demo telemetry (`@example.test`), and Type C Live Portal records across 8 dark-themed MySQL charts, Station Verification transitions, CSV import, User provisioning, Audit Logs, System Settings, and System Health.
- **EV Owner Console (`/owner/dashboard`, `/owner/vehicles`, `/owner/bookings`, `/owner/charging`)**: Fleet CRUD, trigger-validated slot booking (`/api/check-overlap`), stored-procedure charging simulation (`CompleteChargingSession`), downloadable `.txt` receipts, and `"Simulated earnings — not actual company revenue."` disclosures.

---

## Project Structure

```text
DBCAP/
├── api/index.py                  # Vercel Python serverless WSGI entrypoint
├── app/
│   ├── __init__.py               # App factory, CSRFProtect, hardened session cookies
│   ├── db.py                     # DBUtils.PooledDB MySQL 8.0+ pool & TLS parser
│   ├── routes/                   # public, auth, owner, admin, api, auth_middleware
│   ├── services/                 # platform, qr_service, razorpay_service, station, booking, session, payment, report, audit, contact
│   ├── static/                   # CSS, JS (ev_map.js, main.js), local EV photography & SVG logo
│   └── templates/                # Jinja2 views (public, qr_status, privacy/terms, owner, admin)
├── database/
│   ├── 01_schema.sql             # 3NF InnoDB tables
│   ├── 02_constraints_indexes.sql
│   ├── 03_routines_triggers.sql  # CalculateChargingCost, CompleteChargingSession, overlap triggers
│   └── migrations/               # Ordered idempotent migrations (001–006)
├── docs/                         # Architecture, Provenance, Station Verification, Dual QR, Setup & Test Reports
├── tests/                        # Automated pytest verification suite
├── .env.example                  # Non-secret environment contract
├── init_db.py                    # Pure-Python MySQL initializer & migration runner
└── vercel.json                   # Vercel serverless routing config
```

---

## Quickstart & Commands

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Configure environment variables (.env from .env.example)
cp .env.example .env

# 3. Apply idempotent database migrations (creates/upgrades all 21 MySQL tables incl. Migration 008)
python init_db.py --mode migrate

# 4. Run development server
python run.py

# 5. Execute automated test suite
python -m pytest -v
```

For full details on integrated free public APIs (Open Charge Map, OpenStreetMap/Nominatim, OSRM, Open-Meteo, India Post PIN API, ChargeAlong exclusion) and 4-way provenance rules, see [`docs/FREE_APIS_INTEGRATION.md`](./docs/FREE_APIS_INTEGRATION.md).
