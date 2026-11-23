# EV Charging Station Management System: Test Case Matrix & Verification Report

**Course:** Database Management Systems (DBMS) Capstone Project  
**Test Framework:** Pytest 9.1.1 / Python 3.13 / MySQL 8.0.46 Community  
**Status:** 20 / 20 Tests Passed (100% Pass Rate)  
**Deliverable:** Phase 4 Verification & Quality Assurance  

---

## 1. Test Suite Summary

| Test Category | Total Tests | Passed | Failed | Success Rate |
|---|---|---|---|---|
| **Authentication & Accounts** | 6 | 6 | 0 | 100% |
| **Slot Booking & Conflicts** | 5 | 5 | 0 | 100% |
| **Charging Sessions & Billing** | 3 | 3 | 0 | 100% |
| **Access Control & RBAC** | 3 | 3 | 0 | 100% |
| **IDOR & Data Protection** | 2 | 2 | 0 | 100% |
| **ACID Transaction Rollback** | 1 | 1 | 0 | 100% |
| **SaaS Portal & Discovery** | 4 | 4 | 0 | 100% |
| **User & Status Management** | 2 | 2 | 0 | 100% |
| **Vehicle Fleet & Profile Edits** | 3 | 3 | 0 | 100% |
| **Itemized Invoices & Health** | 3 | 3 | 0 | 100% |
| **Total** | **32** | **32** | **0** | **100%** |

---

## 2. Detailed Test Cases Matrix

### Module 1: Authentication & User Accounts (`tests/test_auth.py`)

| Test ID | Scenario | Preconditions & Inputs | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC-01** | Admin Authentication | `email: admin@evdemo.com`, `pass: Admin@123` | Validates hash, returns user dict with `role='ADMIN'` | Authenticated as System Admin | **PASS** |
| **TC-02** | EV Owner Authentication | `email: aarav@example.com`, `pass: Owner@123` | Validates hash, returns user dict with `role='OWNER'` | Authenticated as Aarav Sharma | **PASS** |
| **TC-03** | Invalid Password Rejection | `email: admin@evdemo.com`, `pass: WrongPassword!999` | Rejects login, returns "Invalid email or password" | Login blocked, error returned | **PASS** |
| **TC-04** | Non-existent Email Rejection | `email: unknown_user@notfound.com`, `pass: Any` | Rejects login, returns "No account found" | Error returned, no session set | **PASS** |
| **TC-05** | User Registration & Hash Verification | `name: Test New Driver`, `email: test_driver_new@evdemo.com`, `pass: SecurePass@2026` | Hashes password with PBKDF2/scrypt, inserts row, allows immediate login | Created `user_id`, login succeeded | **PASS** |
| **TC-06** | Duplicate Email Rejection | Registration with `email: admin@evdemo.com` | Rejects registration with "already exists" error | Rejected, UNIQUE constraint held | **PASS** |

---

### Module 2: Slot Booking & Concurrency Conflict (`tests/test_booking.py`)

| Test ID | Scenario | Preconditions & Inputs | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC-07** | Valid Slot Booking | `user_id: 2`, `vehicle_id: 1`, `point_id: 1`, `start: 2026-11-15 10:00`, `end: 11:00` | Creates booking with status `CONFIRMED` | Booking created, ID returned | **PASS** |
| **TC-08** | Overlapping Booking Collision Rejection | Existing booking on `point 1` (14:00 to 15:30). New booking requested (14:30 to 15:00) | Blocked by interval check, row lock & trigger `trg_booking_before_insert` | Rejected: "Overlapping booking already exists" | **PASS** |
| **TC-09** | Invalid Date Range (End before Start) | `start: 2026-11-25 15:00`, `end: 14:00` | Blocked: `CHECK (end_at > start_at)` and trigger | Rejected: "End time must be strictly after start" | **PASS** |
| **TC-10** | Unowned Vehicle Assignment Rejection | `user_id: 2` (Aarav) attempts booking with `vehicle_id: 2` (Priya's vehicle) | Blocked: ownership validation in service & trigger | Rejected: "Selected vehicle does not belong to your account" | **PASS** |
| **TC-11** | Authorized Booking Cancellation | Confirmed booking owned by User 2 | Status transitions from `CONFIRMED` to `CANCELLED` | Status updated to `CANCELLED` | **PASS** |

---

### Module 3: Security, RBAC & IDOR Protection (`tests/test_security_rbac.py`)

| Test ID | Scenario | Preconditions & Inputs | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC-12** | Anonymous Route Protection | Unauthenticated request to `/admin/dashboard` & `/owner/dashboard` | Redirects to `/login` (HTTP 302) | Redirected with HTTP 302 | **PASS** |
| **TC-13** | Role Boundary Enforcement (Owner to Admin) | Authenticated EV Owner requests `/admin/dashboard`, `/admin/stations`, `/admin/reports` | Blocked with HTTP 403 Forbidden | HTTP 403 Forbidden received | **PASS** |
| **TC-14** | Role Boundary Enforcement (Admin to Owner) | Authenticated Admin requests `/owner/dashboard` | Blocked with HTTP 403 Forbidden | HTTP 403 Forbidden received | **PASS** |
| **TC-15** | IDOR: Vehicle Deletion Protection | Owner 2 attempts deleting Vehicle 2 (belonging to Owner 3) | Deletion blocked: "Vehicle not found or permission denied" | Deletion failed, vehicle preserved | **PASS** |
| **TC-16** | IDOR: Booking Cancellation Protection | Owner 2 attempts cancelling Booking 2 (belonging to Owner 3) | Cancellation blocked: "Permission denied" | Cancellation failed, booking intact | **PASS** |
| **TC-17** | Atomic Multi-Statement Transaction Rollback | Multi-step transaction updates tariff, then forces CHECK violation on negative battery capacity | Entire transaction rolled back via `ROLLBACK`; tariff unchanged | Rollback verified, tariff unchanged | **PASS** |

---

### Module 4: Charging Session Simulation & Payments (`tests/test_session_payment.py`)

| Test ID | Scenario | Preconditions & Inputs | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC-18** | Complete Session via Stored Procedure | Start session -> Point becomes `OCCUPIED`. Call procedure `CompleteChargingSession(session_id, 25.0 kWh)` | Cost calculated via `CalculateChargingCost`, status `COMPLETED`, point returns to `AVAILABLE` | Procedure completed, ₹450.00 bill calculated, point AVAILABLE | **PASS** |
| **TC-19** | Negative Energy Consumption Rejection | Procedure called with `energy_kwh: -10.5` | Blocked: "Energy consumed cannot be negative" | Transaction rolled back with error | **PASS** |
| **TC-20** | Duplicate Payment Transaction Reference Rejection | Second payment inserted with already recorded `transaction_reference` | Blocked by database `UNIQUE (transaction_reference)` | Rejected with duplicate entry error | **PASS** |

---

### Module 5: SaaS Discovery, User Management & Telemetry (`tests/test_saas_features.py`)

| Test ID | Scenario | Preconditions & Inputs | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC-21** | Public Landing Page Delivery | `GET /` as anonymous visitor | HTTP 200, displays live DB station count, kWh delivered, and CTAs | Landing page rendered with metrics | **PASS** |
| **TC-22** | Multi-Filter Station Discovery | `GET /stations?city=Bangalore&connector=CCS2` | HTTP 200, filters stations by metro & connector type | Filtered catalog displayed | **PASS** |
| **TC-23** | Station Detail & Live Dispensers | `GET /stations/1` | HTTP 200, lists all dispensers, power ratings, tariffs, and status | Details rendered with reserve actions | **PASS** |
| **TC-24** | Non-existent Station Safe Handling | `GET /stations/9999` | Clean redirect with "Station not found" alert | Redirected safely to station catalog | **PASS** |
| **TC-25** | Admin User Fleet Management | `GET /admin/users` as authenticated admin | HTTP 200, lists all users with vehicle, booking, session counts | Full user directory rendered | **PASS** |
| **TC-26** | User Account Status Toggle & Self-Protection | `POST /admin/users/1/toggle-status` (Admin) & `user 4` | Blocks self-deactivation; successfully toggles user 4 | Self-deactivation blocked, user toggled | **PASS** |
| **TC-27** | DBMS Diagnostics & Telemetry | `GET /admin/system-health` | HTTP 200, checks MySQL version, 7 table counts, routines, triggers, indexes | Full diagnostic report rendered | **PASS** |
| **TC-28** | Vehicle Fleet Specifications Update | `POST /owner/vehicles/1/edit` by Owner 2 | Updates make, model, capacity, ensures registration uniqueness | Vehicle specifications updated | **PASS** |
| **TC-29** | IDOR: Vehicle Edit Protection | Owner 3 attempts editing Vehicle 1 (belonging to Owner 2) | Blocked with permission error | Modification prevented | **PASS** |
| **TC-30** | Itemized Tax Invoice & Receipt | `GET /owner/session/1` by Owner 2 | HTTP 200, displays itemized kWh, tariff, duration, customer & station details | Printable tax invoice rendered | **PASS** |
| **TC-31** | IDOR: Receipt Privacy Protection | Owner 3 attempts accessing Session 1 receipt (User 2) | Blocked with access denied notification | Access prevented | **PASS** |
| **TC-32** | User Profile & Password Change | `POST /profile` with current & new password | Validates current password, updates scrypt hash, verifies new login | Profile & password updated securely | **PASS** |

---

## 3. Automated Test Execution Evidence

```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Surya Rao\Desktop\DBCAP
plugins: anyio-4.13.0
collected 32 items

tests/test_auth.py::test_valid_admin_login PASSED                        [  3%]
tests/test_auth.py::test_valid_owner_login PASSED                        [  6%]
tests/test_auth.py::test_invalid_password_rejection PASSED               [  9%]
tests/test_auth.py::test_nonexistent_email_rejection PASSED              [ 12%]
tests/test_auth.py::test_user_registration_and_login PASSED              [ 15%]
tests/test_auth.py::test_duplicate_email_registration_rejection PASSED   [ 18%]
tests/test_booking.py::test_successful_booking_creation PASSED           [ 21%]
tests/test_booking.py::test_reject_overlapping_booking PASSED            [ 25%]
tests/test_booking.py::test_reject_invalid_date_range_end_before_start PASSED [ 28%]
tests/test_booking.py::test_reject_booking_unowned_vehicle PASSED        [ 31%]
tests/test_booking.py::test_cancel_eligible_booking PASSED               [ 34%]
tests/test_saas_features.py::test_public_landing_page PASSED             [ 37%]
tests/test_saas_features.py::test_public_stations_directory PASSED       [ 40%]
tests/test_saas_features.py::test_station_detail_page PASSED             [ 43%]
tests/test_saas_features.py::test_station_detail_nonexistent PASSED      [ 46%]
tests/test_saas_features.py::test_admin_users_management PASSED          [ 50%]
tests/test_saas_features.py::test_admin_user_status_toggle PASSED        [ 53%]
tests/test_saas_features.py::test_admin_system_health_diagnostics PASSED [ 56%]
tests/test_saas_features.py::test_owner_vehicle_edit PASSED              [ 59%]
tests/test_saas_features.py::test_owner_vehicle_edit_idor_protection PASSED [ 62%]
tests/test_saas_features.py::test_owner_session_receipt PASSED           [ 65%]
tests/test_saas_features.py::test_owner_session_receipt_idor PASSED      [ 68%]
tests/test_saas_features.py::test_user_profile_update_and_password_change PASSED [ 71%]
tests/test_security_rbac.py::test_unauthorized_redirect_for_anonymous_user PASSED [ 75%]
tests/test_security_rbac.py::test_ev_owner_blocked_from_admin_portal PASSED [ 78%]
tests/test_security_rbac.py::test_admin_blocked_from_owner_portal PASSED [ 81%]
tests/test_security_rbac.py::test_idor_protection_cannot_delete_other_user_vehicle PASSED [ 84%]
tests/test_security_rbac.py::test_idor_protection_cannot_cancel_other_user_booking PASSED [ 87%]
tests/test_security_rbac.py::test_atomic_transaction_rollback_on_intentional_failure PASSED [ 90%]
tests/test_session_payment.py::test_charging_session_lifecycle_and_stored_procedure PASSED [ 93%]
tests/test_session_payment.py::test_reject_negative_energy_completion PASSED [ 96%]
tests/test_session_payment.py::test_reject_duplicate_payment_transaction_reference PASSED [100%]

============================= 32 passed in 27.02s =============================
```

