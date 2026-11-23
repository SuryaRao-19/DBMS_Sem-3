# System Architecture — EZ Charge Network Portal (EV ChargeNet)

## 1. High-Level Stack & Blueprint Architecture

The application uses **Python Flask** (App Factory pattern in `app/__init__.py`) backed by **MySQL 8.0+ InnoDB** via `PyMySQL` + `DBUtils.PooledDB` (`app/db.py`), rendered with **Jinja2**, **Chart.js 4**, and **Google Maps JS API / Leaflet.js**, ready for local WSGI or **Vercel Serverless** (`api/index.py`).

| Blueprint | Prefix | Responsibility |
| :--- | :--- | :--- |
| `public_bp` | `/` | Homepage (11 sections), `/stations`, `/stations/<id>`, `/station/<slug>`, `/qr/station/<token>`, `/about`, `/data-sources`, `/contact`, `/privacy`, `/terms`, `/profile` |
| `auth_bp` | `/` | `/login`, `/register` (`OWNER`-only lockdown), `/logout` |
| `owner_bp` | `/owner` | EV Owner dashboard, vehicle CRUD, slot booking, active charging simulation, `/owner/checkout/<session_id>`, `/owner/session/<id>` & `.txt` receipt export |
| `admin_bp` | `/admin` | 8-chart analytics dashboard, station verification transitions, Station QR management (PNG/SVG/Print/Regenerate/Revoke), CSV import, dispensers, bookings, sessions, payments, reports, user management, enquiries, data sources, audit logs, settings, system health |
| `api_bp` | `/api` | `/api/health`, `/api/stations/map`, `/api/check-overlap`, `/api/payments/razorpay/order`, `/api/payments/razorpay/qr`, `/api/payments/razorpay/verify`, `/api/payments/razorpay/sandbox-complete`, `/api/payments/razorpay/webhook` |

---

## 2. Service Layer (`app/services/`)

- `platform_service.py`: Official Tata Power EZ Charge Oct 12, 2026 baseline stats, historical conflict note (`5,500+` / `620+`), verified announcements, corporate social/app links, and `DataSources` governance queries.
- `station_service.py`: Zero-N+1 station & dispenser queries, URL slug generation, approval workflow, and Admin station verification transitions (`VERIFIED`, `PENDING_VERIFICATION`, `HISTORICAL`, `OUTDATED`) with `AuditLogs` persistence.
- `qr_service.py`: Static Station Identification QR token issuance (`StationQRCodes`), opaque scan counting, token rotation/revocation, and local Python `qrcode` PNG/SVG generation.
- `razorpay_service.py`: Server-side GST calculation, Razorpay Test Mode order creation, Dynamic Payment QR generation (`10-min` TTL), HMAC-SHA256 signature verification, `EXPIRED` state enforcement, live-key rejection (`rzp_live_*` blocked), and idempotent webhook processing (`PaymentWebhookEvents`).
- `booking_service.py` & `session_service.py`: Trigger-validated overlap checks (`trg_booking_before_insert`), row-locked session initiation (`SELECT ... FOR UPDATE`), and stored-procedure billing completion (`CompleteChargingSession` + `CalculateChargingCost`).
- `report_service.py`: Separated KPIs (`verified_stations`, `pending_verification_stations`, `demo_users`, `live_users`, `new_enquiries`), portable `DATABASE()` system health diagnostics across 16 tables, and all 8 Admin Chart.js datasets.
- `contact_service.py` & `audit_service.py`: Server-side Web3Forms proxy, DB-backed spam/rate-limit protection, and audit trail recording.

---

## 3. UI & Navigation Architecture

- **Layout (`app/templates/base.html`)**: Collapsible fixed left sidebar (`#0B1220` Midnight Navy) organized into 7 logical groups (`Overview`, `Charging Network`, `Operations`, `Finance`, `Management`, `Analytics`, `Account`), plus sticky top header with breadcrumbs, table/view search, notification indicator, and account dropdown.
- **Role-Responsive Surfaces**: Dark showcase styling on the public landing portal paired with a high-contrast Light `#F4F7FA` / `#FFFFFF` Admin Workspace and WCAG-accessible interactive controls tested across `1920px`, `1440px`, `1024px`, `768px`, and `375px` viewports.
