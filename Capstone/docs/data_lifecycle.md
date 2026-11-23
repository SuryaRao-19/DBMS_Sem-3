# APPLICATION DATA LIFECYCLE & WORKFLOW TRACEABILITY
## EV Charging Station Management System — Major Upgrade 2.0
**Target Database:** `ev_charging_db` on MySQL 8.0+ (InnoDB)  
**File:** `docs/data_lifecycle.md`

---

## 1. Global Data Flow Pattern

All write and read operations follow the strict layered architectural flow:

```
[ Frontend Page ]
       │
       ▼  (HTTP POST / GET with CSRF & Session Cookie)
[ Flask Route Controller ]
       │
       ▼  (Input Validation, Sanitization, Type Coercion)
[ Service Layer Function ]
       │
       ▼  (Atomic with transaction(): context manager)
[ MySQL 8+ Database Engine (InnoDB) ]
       ├── Row-Level Locks (SELECT ... FOR UPDATE)
       ├── Deterministic Functions (CalculateChargingCost)
       ├── Before-Insert Triggers (trg_booking_before_insert)
       └── Relational Tables (InnoDB ACID Storage)
       │
       ▼  (Commit / Rollback & DictCursor Results)
[ Service Return Value ]
       │
       ▼  (Flash messages or JSON Response)
[ Frontend View Rendering / Client Redirection ]
```

---

## 2. End-to-End Traceability of Core Workflows

### Workflow 1: Driver Account Registration
1. **Frontend Page:** `/register` (`app/templates/auth/register.html`)
2. **Backend Route:** `POST /register` in `app/routes/auth.py`
3. **Input Validation:** Verifies non-empty full name, valid email format, 10-digit phone, password confirmation match, password length $\ge 8$.
4. **SQL Executed:**
   ```sql
   SELECT user_id FROM Users WHERE email = %s;
   INSERT INTO Users (full_name, email, phone, password_hash, role, account_status)
   VALUES (%s, %s, %s, %s, 'OWNER', 'ACTIVE');
   ```
5. **Tables Read/Modified:** `Users` (Read to detect duplicates, Modified with `INSERT`).
6. **Constraints Enforced:** `UNIQUE KEY (email)`, `CHECK (role IN ('ADMIN', 'OWNER'))`.
7. **Transaction:** Autocommit on single atomic `INSERT` via `execute()`.
8. **Frontend Response:** Flash message `"Account created successfully. Please log in."` -> HTTP 302 Redirect to `/login`.
9. **Workbench Verification:**
   ```sql
   SELECT user_id, full_name, email, role, created_at FROM ev_charging_db.Users ORDER BY user_id DESC LIMIT 1;
   ```

---

### Workflow 2: Electric Vehicle Fleet Registration
1. **Frontend Page:** `/owner/vehicles` (`app/templates/owner/vehicles.html`)
2. **Backend Route:** `POST /owner/vehicles` in `app/routes/owner.py`
3. **Input Validation:** Verifies authenticated `user_id`, non-empty make/model, clean uppercase registration number, battery capacity $> 0$.
4. **SQL Executed:**
   ```sql
   INSERT INTO Vehicles (user_id, registration_no, make, model, battery_capacity_kwh)
   VALUES (%s, %s, %s, %s, %s);
   ```
5. **Tables Read/Modified:** `Vehicles` (`INSERT`).
6. **Constraints Enforced:** `FK (user_id) REFERENCES Users(user_id) ON DELETE CASCADE`, `UNIQUE KEY (registration_no)`, `CHECK (battery_capacity_kwh > 0)`.
7. **Transaction:** Atomic `execute()`.
8. **Frontend Response:** Flash success message -> HTTP 302 Redirect to `/owner/vehicles`.
9. **Workbench Verification:**
   ```sql
   SELECT * FROM ev_charging_db.Vehicles WHERE user_id = 2;
   ```

---

### Workflow 3: Charging Station Discovery & Real-Time Availability
1. **Frontend Page:** `/stations` (`app/templates/public_stations.html`)
2. **Backend Route:** `GET /stations` in `app/routes/public.py`
3. **Input Validation:** Sanitizes optional query filters (`city`, `status`).
4. **SQL Executed (Read-Only):**
   ```sql
   SELECT * FROM Stations WHERE 1=1 AND city = %s ORDER BY station_name;
   SELECT 
       COUNT(point_id) AS total_points,
       SUM(CASE WHEN point_status = 'AVAILABLE' THEN 1 ELSE 0 END) AS available_points,
       SUM(CASE WHEN point_status = 'OCCUPIED' THEN 1 ELSE 0 END) AS occupied_points
   FROM ChargingPoints WHERE station_id = %s;
   ```
5. **Tables Read/Modified:** `Stations` (Read), `ChargingPoints` (Read). No data modified.
6. **Workbench Verification:**
   ```sql
   SELECT s.station_name, COUNT(cp.point_id) as total,
          SUM(cp.point_status = 'AVAILABLE') as free
   FROM Stations s JOIN ChargingPoints cp ON s.station_id = cp.station_id
   GROUP BY s.station_id, s.station_name;
   ```

---

### Workflow 4: Booking Creation (Row-Locking & Overlap Prevention)
1. **Frontend Page:** `/stations/<id>` or `/owner/bookings` (`app/templates/owner/bookings.html`)
2. **Backend Route:** `POST /owner/book/<point_id>` in `app/routes/owner.py`
3. **Input Validation:**
   - Validates that `start_at` and `end_at` are valid ISO datetimes.
   - Checks `start_at >= NOW()` (reservations must start in future).
   - Checks `end_at > start_at`.
   - Checks that selected vehicle belongs to the logged-in user.
4. **SQL Executed inside Atomic Transaction:**
   ```sql
   START TRANSACTION;
   -- 1. Row-level lock on dispenser to serialize concurrent booking threads
   SELECT point_id, status FROM ChargingPoints WHERE point_id = %s FOR UPDATE;
   
   -- 2. Check for time interval collision
   SELECT booking_id FROM Bookings
   WHERE point_id = %s AND booking_status IN ('PENDING', 'CONFIRMED')
     AND %s < end_at AND %s > start_at;
   
   -- 3. If 0 conflicts, insert booking
   INSERT INTO Bookings (user_id, vehicle_id, point_id, start_at, end_at, booking_status)
   VALUES (%s, %s, %s, %s, %s, 'CONFIRMED');
   COMMIT;
   ```
5. **Constraints & Triggers Executed:**
   - Trigger `trg_booking_before_insert` executes inside MySQL to verify vehicle ownership and operational availability as defense-in-depth.
6. **Workbench Verification:**
   ```sql
   SELECT * FROM ev_charging_db.Bookings WHERE point_id = 1 ORDER BY booking_id DESC LIMIT 1;
   ```

---

### Workflow 5: Booking Cancellation
1. **Frontend Page:** `/owner/bookings` (`app/templates/owner/bookings.html`)
2. **Backend Route:** `POST /owner/bookings/<id>/cancel` in `app/routes/owner.py`
3. **Input Validation:** Verifies ownership (`b.user_id == current_user_id`), ensures booking status is `PENDING` or `CONFIRMED`.
4. **SQL Executed:**
   ```sql
   UPDATE Bookings SET booking_status = 'CANCELLED'
   WHERE booking_id = %s AND user_id = %s AND booking_status IN ('PENDING', 'CONFIRMED');
   ```
5. **Business Rule:** Once marked `CANCELLED`, the time slot is immediately liberated for other drivers.
6. **Workbench Verification:**
   ```sql
   SELECT booking_id, booking_status FROM ev_charging_db.Bookings WHERE booking_id = %s;
   ```

---

### Workflow 6: Charging Session Initialization & Completion
1. **Frontend Page:** `/owner/charging` (`app/templates/owner/charging.html`)
2. **Backend Route:** `POST /api/session/complete` or `/owner/charging/complete`
3. **Input Validation:** Energy delivered must be $\ge 0$, session must be in state `IN_PROGRESS`.
4. **Stored Procedure Invocation:**
   ```sql
   CALL CompleteChargingSession(p_session_id, p_energy_kwh);
   ```
5. **Database Actions Inside Procedure:**
   - Locks `ChargingSessions` row with `FOR UPDATE`.
   - Calls deterministic function `CalculateChargingCost(p_energy_kwh, tariff)`.
   - Updates `energy_kwh`, `total_cost`, `end_at = CURRENT_TIMESTAMP`, and `session_status = 'COMPLETED'`.
   - Atomically updates `ChargingPoints.point_status = 'AVAILABLE'`.
6. **Workbench Verification:**
   ```sql
   SELECT session_id, energy_kwh, tariff_per_kwh, total_cost, session_status, end_at 
   FROM ev_charging_db.ChargingSessions WHERE session_id = %s;
   ```

---

### Workflow 7: Payment Settlement & Tax Invoice Generation
1. **Frontend Page:** `/owner/history` -> `/owner/session/<id>` (`app/templates/owner/receipt.html`)
2. **Backend Route:** `POST /owner/session/<id>/pay` in `app/routes/owner.py`
3. **Input Validation:** Verifies session exists, status is `COMPLETED`, amount equals `cs.total_cost`, no existing payment record with status `SUCCESS`.
4. **SQL Executed:**
   ```sql
   INSERT INTO Payments (session_id, transaction_reference, amount, payment_method, payment_status, paid_at)
   VALUES (%s, %s, %s, %s, 'SUCCESS', CURRENT_TIMESTAMP);
   ```
5. **Constraints Enforced:** `UNIQUE (transaction_reference)`, `CHECK (amount >= 0)`.
6. **Workbench Verification:**
   ```sql
   SELECT * FROM ev_charging_db.Payments WHERE session_id = %s;
   ```

---

### Workflow 8: Administrative Audit Logging & Policy Updates
1. **Frontend Page:** `/admin/audit-logs` (`app/templates/admin/audit_logs.html`)
2. **Backend Route:** `POST /admin/settings/update`
3. **Input Validation:** Admin authentication verified, setting key validated against `SystemSettings`.
4. **SQL Executed:**
   ```sql
   UPDATE SystemSettings SET setting_value = %s WHERE setting_key = %s;
   INSERT INTO AuditLogs (user_id, action, entity_name, details, ip_address)
   VALUES (%s, 'UPDATE_SETTING', 'SystemSettings', %s, %s);
   ```
5. **Workbench Verification:**
   ```sql
   SELECT * FROM ev_charging_db.AuditLogs ORDER BY log_id DESC LIMIT 5;
   SELECT * FROM ev_charging_db.SystemSettings;
   ```
