# BACKEND API & ROUTE TO DATABASE TABLE MAPPING
## EV Charging Station Management System — Major Upgrade 2.0
**Target Database:** `ev_charging_db` on MySQL 8.0+ (InnoDB)  
**File:** `docs/api_to_table_mapping.md`

---

## 1. Table-to-Route Summary Matrix

| Table Name | Read By (Endpoints) | Written By (Endpoints) |
| :--- | :--- | :--- |
| **`Users`** | `/login`, `/admin/users`, `/profile`, `/admin/dashboard`, `/admin/reports` | `POST /register`, `POST /profile`, `POST /profile/password`, `POST /admin/users/<id>/toggle-status` |
| **`Vehicles`** | `/owner/vehicles`, `/owner/bookings`, `/owner/dashboard`, `/owner/session/<id>` | `POST /owner/vehicles`, `POST /owner/vehicles/<id>/edit`, `POST /owner/vehicles/<id>/delete` |
| **`Stations`** | `/stations`, `/stations/<id>`, `/admin/stations`, `/admin/reports`, `/owner/session/<id>` | `POST /admin/stations`, `POST /admin/stations/<id>/edit` |
| **`ChargingPoints`** | `/stations`, `/stations/<id>`, `/admin/points`, `/api/points/status`, `/api/check-overlap` | `POST /admin/points`, `POST /admin/points/<id>/edit`, `CompleteChargingSession` (Procedure) |
| **`Bookings`** | `/owner/bookings`, `/admin/bookings`, `/owner/dashboard`, `/api/check-overlap` | `POST /owner/book/<id>`, `POST /owner/bookings/<id>/cancel` |
| **`ChargingSessions`**| `/owner/charging`, `/owner/history`, `/owner/session/<id>`, `/admin/sessions`, `/admin/reports` | `POST /owner/charging/start`, `POST /api/session/complete`, `CompleteChargingSession` (Procedure) |
| **`Payments`** | `/owner/history`, `/owner/session/<id>`, `/admin/payments`, `/admin/reports`, `/admin/dashboard` | `POST /owner/session/<id>/pay`, `POST /api/session/pay` |
| **`AuditLogs`** | `GET /admin/audit-logs` | `POST /admin/stations`, `POST /admin/stations/<id>/edit`, `POST /admin/points`, `POST /admin/points/<id>/edit`, `POST /admin/users/<id>/toggle-status`, `POST /admin/settings/update` |
| **`SystemSettings`** | `GET /admin/audit-logs`, Service lookups | `POST /admin/settings/update` |

---

## 2. Detailed Route-by-Route Specification

### 2.1 Public & Authentication Endpoints

#### `POST /register`
* **Controller:** `app/routes/auth.py:register`
* **Database Operations:**
  * Reads `Users` (`SELECT user_id FROM Users WHERE email = ?`)
  * Writes `Users` (`INSERT INTO Users (...)`)
* **Transaction Mode:** Autocommit

#### `POST /login`
* **Controller:** `app/routes/auth.py:login`
* **Database Operations:**
  * Reads `Users` (`SELECT * FROM Users WHERE email = ?`)
* **Transaction Mode:** Read-Only

#### `POST /profile` & `POST /profile/password`
* **Controller:** `app/routes/public.py:profile` & `change_password`
* **Database Operations:**
  * Reads `Users` (`SELECT password_hash FROM Users WHERE user_id = ?`)
  * Writes `Users` (`UPDATE Users SET full_name = ?, phone = ?` or `password_hash = ?`)

---

### 2.2 EV Owner (Customer) Endpoints

#### `GET /owner/dashboard`
* **Controller:** `app/routes/owner.py:dashboard`
* **Database Operations (Read-Only):**
  * Reads `Vehicles` (`COUNT(*)`)
  * Reads `Bookings` (`SELECT * WHERE user_id = ? AND booking_status = 'CONFIRMED'`)
  * Reads `ChargingSessions` (`SUM(energy_kwh)`)
  * Reads `Payments` (`SUM(amount)`)

#### `POST /owner/vehicles`
* **Controller:** `app/routes/owner.py:vehicles`
* **Database Operations:**
  * Writes `Vehicles` (`INSERT INTO Vehicles (user_id, registration_no, make, model, battery_capacity_kwh)`)

#### `POST /owner/vehicles/<id>/edit`
* **Controller:** `app/routes/owner.py:edit_vehicle`
* **Database Operations:**
  * Reads `Vehicles` (`SELECT user_id FROM Vehicles WHERE vehicle_id = ?`)
  * Writes `Vehicles` (`UPDATE Vehicles SET make = ?, model = ?, battery_capacity_kwh = ? WHERE vehicle_id = ?`)

#### `POST /owner/vehicles/<id>/delete`
* **Controller:** `app/routes/owner.py:delete_vehicle`
* **Database Operations:**
  * Reads `Vehicles` & `Bookings` (verifies ownership and checks for active reservations)
  * Writes `Vehicles` (`DELETE FROM Vehicles WHERE vehicle_id = ?`)

#### `POST /owner/book/<point_id>`
* **Controller:** `app/routes/owner.py:book_point`
* **Database Operations (Multi-Statement Atomic Transaction):**
  * `SELECT point_id, status FROM ChargingPoints WHERE point_id = ? FOR UPDATE;`
  * Reads `Bookings` (collision detection query)
  * Writes `Bookings` (`INSERT INTO Bookings (...)`)
  * *Trigger Executed:* `trg_booking_before_insert`

#### `POST /owner/bookings/<id>/cancel`
* **Controller:** `app/routes/owner.py:cancel_booking_route`
* **Database Operations:**
  * Writes `Bookings` (`UPDATE Bookings SET booking_status = 'CANCELLED' WHERE booking_id = ? AND user_id = ?`)

#### `POST /owner/charging/start`
* **Controller:** `app/routes/owner.py:start_charging_route`
* **Database Operations:**
  * Reads `Bookings` and `ChargingPoints`
  * Writes `ChargingSessions` (`INSERT INTO ChargingSessions (...)`)
  * Writes `ChargingPoints` (`UPDATE ChargingPoints SET point_status = 'OCCUPIED'`)
  * Writes `Bookings` (`UPDATE Bookings SET booking_status = 'COMPLETED'`)

#### `POST /owner/charging/complete`
* **Controller:** `app/routes/owner.py:complete_charging_route`
* **Database Operations:**
  * `CALL CompleteChargingSession(session_id, energy_kwh);`
  * Internal writes: `ChargingSessions.energy_kwh`, `ChargingSessions.total_cost`, `ChargingSessions.session_status = 'COMPLETED'`, `ChargingPoints.point_status = 'AVAILABLE'`.

#### `POST /owner/session/<id>/pay`
* **Controller:** `app/routes/owner.py:pay_session_route`
* **Database Operations:**
  * Reads `ChargingSessions` (verifies cost)
  * Writes `Payments` (`INSERT INTO Payments (session_id, transaction_reference, amount, payment_method, payment_status)`)

---

### 2.3 Administrator Endpoints

#### `GET /admin/dashboard`
* **Controller:** `app/routes/admin.py:dashboard`
* **Database Operations (Read-Only):**
  * Reads `Payments` (`SUM(amount)`)
  * Reads `ChargingSessions` (`SUM(energy_kwh)`)
  * Reads `Stations` (`COUNT(*)`)
  * Reads `ChargingPoints` (`SUM(point_status = 'AVAILABLE')`)
  * Reads `Bookings` & `ChargingSessions` (recent activity)

#### `POST /admin/stations` & `POST /admin/stations/<id>/edit`
* **Controller:** `app/routes/admin.py:stations` & `edit_station`
* **Database Operations:**
  * Writes `Stations` (`INSERT` or `UPDATE`)
  * Writes `AuditLogs` (`INSERT INTO AuditLogs (...)`)

#### `POST /admin/points` & `POST /admin/points/<id>/edit`
* **Controller:** `app/routes/admin.py:points` & `edit_point`
* **Database Operations:**
  * Writes `ChargingPoints` (`INSERT` or `UPDATE`)
  * Writes `AuditLogs` (`INSERT INTO AuditLogs (...)`)

#### `POST /admin/users/<id>/toggle-status`
* **Controller:** `app/routes/admin.py:toggle_status`
* **Database Operations:**
  * Reads `Users` (`SELECT role, account_status FROM Users WHERE user_id = ?`)
  * Writes `Users` (`UPDATE Users SET account_status = ? WHERE user_id = ?`)
  * Writes `AuditLogs` (`INSERT INTO AuditLogs (...)`)

#### `GET /admin/audit-logs`
* **Controller:** `app/routes/admin.py:audit_logs`
* **Database Operations (Read-Only):**
  * Reads `AuditLogs` (`SELECT a.*, u.full_name FROM AuditLogs a LEFT JOIN Users u ...`)
  * Reads `SystemSettings` (`SELECT * FROM SystemSettings ORDER BY setting_key`)

#### `POST /admin/settings/update`
* **Controller:** `app/routes/admin.py:update_setting_route`
* **Database Operations:**
  * Writes `SystemSettings` (`UPDATE SystemSettings SET setting_value = ? WHERE setting_key = ?`)
  * Writes `AuditLogs` (`INSERT INTO AuditLogs (...)`)

---

### 2.4 REST API Endpoints

#### `GET /api/health`
* **Controller:** `app/routes/api.py:health_check`
* **Database Operations (Read-Only):**
  * `SELECT 1 as healthy, VERSION() as mysql_version, DATABASE() as db;`

#### `GET /api/check-overlap`
* **Controller:** `app/routes/api.py:check_overlap`
* **Database Operations (Read-Only):**
  * `SELECT booking_id FROM Bookings WHERE point_id = ? AND booking_status IN ('PENDING', 'CONFIRMED') AND ? < end_at AND ? > start_at;`
