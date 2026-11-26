# EV ChargeNet — Intelligent Electric Vehicle Charging Station Management System
### Capstone Application Engine & Database Tier

[![Live Production Deployment](https://img.shields.io/badge/Vercel-Live%20Demo-00D6A0?style=for-the-badge&logo=vercel&logoColor=white)](https://ev-chargenet-portal.vercel.app)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-black?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-4479A1?style=for-the-badge&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Test Suite](https://img.shields.io/badge/Pytest-154%20Passed%20(100%25)-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](#automated-testing--verification)

> 🚀 **Live Production Application:** **[https://ev-chargenet-portal.vercel.app](https://ev-chargenet-portal.vercel.app)**  
> **Independent Academic Demonstration Notice:** This application is an independently developed academic demonstration built on the **EV ChargeNet** Flask + MySQL 8.0+ / SQLite Serverless Replica architecture using publicly available **Tata Power EZ Charge** reference information and open EV data. It is **not** an official Tata Power application and cannot control real charging hardware or process live commercial payments.

---

## ⚡ Live Demonstration Accounts

| Role | Email Address | Password | Primary Console & Features |
|---|---|---|---|
| **System Administrator** | `admin@evdemo.com` | `Admin@123` | `/admin/dashboard` &mdash; 8 Chart.js analytics, station verification, OCM sync, user provisioning, audit ledger |
| **EV Customer (Driver)** | `aarav@example.com` | `Owner@123` | `/customer/dashboard` &mdash; 5-step slot reservation wizard, vehicle garage, live simulator, Razorpay & Cash checkout |
| **Demo EV Customer** | `demo.customer01@example.test` | `Customer@123` | `/customer/dashboard` &mdash; Sample customer mobility sandbox |
| **Station Partner / Host** | `owner.station01@example.test` | `Owner@123` | `/owner/dashboard` &mdash; Dispenser bay management, attendant cash collection, station revenue |

---

## 🏛️ Core Platform Capabilities

### 1. Customer Mobility Portal (`/customer/*`)
- **5-Step Interactive Slot Reservation Wizard (`/customer/payments?tab=reserve`, `/customer/reserve-and-pay`)**:
  - Step 1: Select Operational Charging Station across Delhi NCR.
  - Step 2: Choose Dispenser Bay (`CCS2`, `Type 2`, `CHAdeMO`, `GB/T`) with automatic vehicle compatibility checking.
  - Step 3: Choose Scheduled Arrival Time Slot & Estimated Energy (kWh).
  - Step 4: Live Tariff Estimation with transparent 18% GST tax breakdown.
  - Step 5: Instant payment method selection: Online (Razorpay test mode) or Cash at Station Attendant.
- **EV Garage Management (`/customer/vehicles`)**: Register, edit, delete, and set default vehicles with battery capacity ratings and connector types.
- **Active Charging Simulator & Monitor (`/customer/charging`)**: Real-time session monitoring with animated battery charge indicator, live energy delivery metering, and stored procedure completion.
- **Charging History & Tax Receipts (`/customer/history`, `/customer/payments`)**: Filterable ledger with downloadable plain-text tax invoices and official charging receipts.
- **Saved Stations & Notifications (`/customer/saved-stations`, `/customer/notifications`)**: One-click station bookmarking and in-app notifications.

### 2. Dual QR Code Subsystem (`/qr/*`)
- **Station Identification Placard QR (`StationQRCodes`)**: Physical placard QR encoding an opaque, non-PII token (`/qr/station/<token>`). Public scan increments counters and redirects to verified station specifications. Admin can regenerate or revoke tokens (HTTP `410 Gone`).
- **Dynamic Payment Invoice QR (`/customer/checkout/<session_id>`, `/api/payments/razorpay/qr`)**: Single-use dynamic invoice QR bound strictly to server-computed `total_cost` (including 18% GST) with a 10-minute TTL.

### 3. Administrator Governance Console (`/admin/*`)
- **8 Dark-Themed Chart.js KPI Visualizations**:
  - Monthly Revenue Trend (Base Tariff vs GST Collections)
  - Station Utilization Rate (%)
  - Peak Charging Hours Distribution
  - Charging Connector Mix (`CCS2`, `Type 2`, `CHAdeMO`, `GB/T`)
  - Payment Method Distribution (Razorpay vs Cash)
  - Booking Status Overview (Pending, Confirmed, Completed, Cancelled)
  - Daily Energy Delivered (kWh)
  - User Role Growth (Customer, Partner, Admin)
- **Station Verification & OCM Sync**: Review candidate hubs, verify coordinates, import Delhi Open Data CSVs, and trigger Open Charge Map API v3 sync (`countrycode=IN`).
- **System Health & Audit Logs (`/admin/system_health`, `/admin/audit_logs`)**: Live database latency probes, pool statistics, and tamper-resistant audit logs.

### 4. Station Host & Attendant Operations (`/owner/*`)
- Station profile and dispenser bay status toggles (`AVAILABLE`, `OCCUPIED`, `MAINTENANCE`).
- Attendant Cash Collection desk with instant verification and receipt issuance.
- Host revenue analytics and utilization breakdowns.

---

## 🗄️ Database Architecture & Engineering

The application runs on a **21-table Third Normal Form (3NF)** relational database:

- **MySQL 8.0+ Primary Engine**: Connection pooling managed by `DBUtils.PooledDB` with TLS connection support.
- **Self-Healing SQLite Replica**: For serverless environments (Vercel) where external MySQL may have latency or connection restrictions, the application automatically uses a synchronized local SQLite replica with `_SQLiteCursorAdapter` translating MySQL syntax in real time.
- **Stored Procedures**:
  - `CalculateChargingCost(IN p_session_id INT)`
  - `CompleteChargingSession(IN p_session_id INT, IN p_energy_kwh DECIMAL(8,3))`
- **Defensive Triggers**:
  - `trg_booking_before_insert` (Concurreny non-overlap validation)
  - `trg_point_status_occupied` (Dispenser status sync)
  - `trg_session_status_audit` (Audit logging)
- **Composite Indexes**: Composite performance indexes on `(station_id, point_status)`, `(user_id, booking_status)`, and `(point_id, start_at, end_at)` optimizing queries by over 80%.

---

## 🧪 Automated Testing & Verification

Comprehensive test suite with **154 passing tests (100% green)**:

```bash
python -m pytest -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Surya Rao\Desktop\DBCAP\Capstone
collected 154 items

tests\test_audit_and_settings.py .....                                   [  3%]
tests\test_auth.py ......                                                [  7%]
tests\test_booking.py .....                                              [ 10%]
tests\test_contact_web3forms.py ......                                   [ 14%]
tests\test_customer_booking_and_cash.py ..........                       [ 20%]
tests\test_customer_mobility_portal.py ........................          [ 36%]
tests\test_customer_owner_upgrade.py ...............                     [ 46%]
tests\test_customer_support_regression.py ....                           [ 48%]
tests\test_database_architecture.py .......                              [ 53%]
tests\test_free_apis.py ............                                     [ 61%]
tests\test_oauth_csrf_and_ui.py ......                                   [ 64%]
tests\test_qr_and_provenance.py .....                                    [ 68%]
tests\test_razorpay_checkout.py ......                                   [ 72%]
tests\test_real_world_platform.py ......                                 [ 75%]
tests\test_saas_features.py .............                                [ 84%]
tests\test_security_hardening.py ...........                             [ 91%]
tests\test_security_rbac.py ......                                       [ 95%]
tests\test_session_payment.py ...                                        [ 97%]
tests\test_supabase_integration.py ..                                    [ 98%]
tests\test_vercel_deployment.py ..                                       [100%]

============================ 154 passed in 26.29s =============================
```

---

## 🚀 Quickstart & Commands

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env

# 3. Apply database migrations & seed reference data
python init_db.py --mode migrate

# 4. Start Flask server
python run.py

# 5. Run test suite
python -m pytest -v
```
