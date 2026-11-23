# EV Charging Station Management System: Comprehensive Capstone Project Report

**Course:** Database Management Systems (DBMS) Capstone Project  
**Author:** Student DBMS Capstone Project  
**Target RDBMS:** MySQL 8.0.46 Community Edition (InnoDB Engine)  
**Backend Framework:** Python 3.13 / Flask 3.1  
**Total Marks:** 100 Marks (Phases 1 through 5 Complete)  

---

## 1. Executive Summary & Problem Statement

Electric Vehicle (EV) adoption requires robust charging infrastructure to overcome range anxiety, eliminate slot contention, and manage charging tariffs and billing. 

Traditional EV reservation systems often suffer from:
1. **Slot contention & double-booking:** Unsynchronized reservation windows causing physical driver conflicts at charging stations.
2. **Disconnected financial auditing:** Discrepancies between physical energy delivered ($kWh$), dynamic tariffs, and settlement receipts.
3. **Weak database enforcement:** Relying solely on clientside UI code rather than relational database constraints, triggers, and ACID transactions.

This project delivers a **fully integrated, database-driven EV Charging Station Management System** that unites a Third Normal Form (3NF) relational schema, procedural SQL routines, validation triggers, analytical reports, secondary index optimizations, and role-based access control with a modern web interface.

---

## 2. System Architecture

The application adopts a three-tier layered architecture:

```
+-----------------------------------------------------------------------+
|                         PRESENTATION TIER                             |
|    Responsive Web Portal (Vanilla HTML5 / Modern CSS / Vanilla JS)    |
|    - Station Infrastructure Directory & Tariff Configuration (Admin)  |
|    - Slot Reservation, Vehicle Registry & Live Simulator (Owner)      |
+-----------------------------------------------------------------------+
                                  │  HTTP / REST (JSON)
                                  ▼
+-----------------------------------------------------------------------+
|                         APPLICATION TIER                              |
|                Python 3.13 / Flask Web Application                    |
|    - Blueprint Routing (Auth, Admin, Owner, API)                      |
|    - Domain Services (Auth, Stations, Vehicles, Bookings, Sessions)   |
|    - Session Security, PBKDF2/scrypt Password Hashing, RBAC           |
+-----------------------------------------------------------------------+
                                  │  PyMySQL (Parameterized SQL)
                                  ▼
+-----------------------------------------------------------------------+
|                          DATABASE TIER                                |
|             MySQL 8.0+ Community Server (InnoDB Storage Engine)       |
|    - Relational Tables in 3NF (7 Tables with PK, FK, CHECK, UNIQUE)   |
|    - Stored Function: CalculateChargingCost()                         |
|    - Stored Procedure: CompleteChargingSession() (with FOR UPDATE)    |
|    - Validation Triggers: trg_booking_before_insert, etc.             |
|    - Secondary Composite B-Tree Indexes & Analytical Reports          |
+-----------------------------------------------------------------------+
```

---

## 3. Phase 1: Data Modeling & 3NF Normalization

### 3.1 Entity Relationship Diagram
The system models 7 core business entities:
- `Users` (1:M with `Vehicles`, 1:M with `Bookings`, 1:M with `ChargingSessions`)
- `Stations` (1:M with `ChargingPoints`)
- `ChargingPoints` (1:M with `Bookings`, 1:M with `ChargingSessions`)
- `Vehicles` (1:M with `Bookings`, 1:M with `ChargingSessions`)
- `Bookings` (1:1 optional with `ChargingSessions`)
- `ChargingSessions` (1:M with `Payments`)

Detailed cardinalities and attributes are documented in `docs/er_diagram.mmd`.

### 3.2 3NF Normalization Analysis
1. **First Normal Form (1NF):** All attributes contain strictly atomic scalar values (no multivalued attributes or repeating groups). Primary keys are defined for all relations.
2. **Second Normal Form (2NF):** All relations with composite candidate keys (e.g. `ChargingPoints (station_id, point_code)`) have no partial dependencies. Dispensers attributes describe the dispenser in that station and depend on the full key; station attributes (`address`, `city`) are factored into the `Stations` relation.
3. **Third Normal Form (3NF):** No transitive functional dependencies exist between non-prime attributes ($X \rightarrow Y$ only where $X$ is a superkey). In `ChargingSessions`, `tariff_per_kwh` and `total_cost` are retained as an immutable temporal ledger to preserve historical billing integrity against future tariff updates.

---

## 4. Phase 2: Procedural SQL Implementation

### 4.1 Stored Function: `CalculateChargingCost`
Computes monetary billing based on energy consumed ($kWh$) and tariff rate per kilowatt-hour:
$$\text{Cost} = \text{ROUND}(\text{energy\_kwh} \times \text{tariff\_per\_kwh}, 2)$$
Declared as `DETERMINISTIC NO SQL` to enable compiler-level subquery caching by the query optimizer.

### 4.2 Booking Conflict Trigger: `trg_booking_before_insert`
Enforces:
1. `end_at > start_at` validation.
2. Vehicle ownership verification (`Vehicles.user_id = NEW.user_id`).
3. Dispenser and station operational availability check (`point_status = 'AVAILABLE'`, `station_status = 'ACTIVE'`).
4. Overlap contention prevention using interval intersection:
   $$\text{NEW.start\_at} < \text{existing.end\_at} \quad \text{AND} \quad \text{NEW.end\_at} > \text{existing.start\_at}$$
   Raises `SIGNAL SQLSTATE '45000'` upon collision.

### 4.3 Stored Procedure: `CompleteChargingSession`
Executes an atomic transition:
- Acquires an exclusive row-level lock via `SELECT ... FOR UPDATE` on `ChargingSessions`.
- Validates session is in `IN_PROGRESS` status.
- Invokes `CalculateChargingCost`.
- Updates `energy_kwh`, `end_at = NOW()`, `total_cost`, and `session_status = 'COMPLETED'`.
- Restores `ChargingPoints.point_status = 'AVAILABLE'`.
- Includes `DECLARE EXIT HANDLER FOR SQLEXCEPTION` with `ROLLBACK` for ACID durability.

---

## 5. Phase 3: Analytical Reports & Indexing Optimization

### 5.1 Analytical Reports
Eight comprehensive reports were implemented in `database/04_reports.sql`:
1. **Station Infrastructure Directory:** Dispenser hardware and connectors per station.
2. **EV Owner Charging History:** 5-table join tracking personal session duration, energy, and total spend.
3. **Monthly Revenue by Station:** Aggregated financial revenue grouped by station and calendar month (`YYYY-MM`).
4. **Monthly Energy Delivered:** Kilowatt-hour aggregation across stations.
5. **Booking Status Distribution:** Percentage breakdown of completed, confirmed, and cancelled bookings.
6. **Charging Point Availability:** Live dispenser status counts by city.
7. **Owner Total Spend Ranking:** Aggregate expenditure rankings across EV drivers.
8. **Station Utilization Summary:** Total charging hours and energy delivered.

### 5.2 Query Execution Plan Demonstration
Captured from live MySQL 8.0.46 Community Server:
- **Query:** Financial settlement filter on `Payments` where `payment_status = 'SUCCESS' AND paid_at >= '2026-08-01'`.
- **Before Index:** Optimizer executed an `ALL` Full Table Scan with `Using where` (16.67% filtered).
- **Index Applied:** Composite B-Tree index `idx_payment_status_date (payment_status, paid_at)`.
- **After Index:** Optimizer switched to `range` Index Range Scan with `Using index condition` (100.00% filtered). Full before/after evidence is recorded in `docs/query_plan_comparison.md`.

---

## 6. Phase 4: Security, Access Control & Testing

### 6.1 Security Controls
- **Role-Based Access Control (RBAC):** Admin/Station Operator vs EV Owner.
- **Server-Side Authorization:** User identities are strictly retrieved from authenticated server session tokens, preventing Insecure Direct Object Reference (IDOR) attacks.
- **SQL Injection Prevention:** 100% of queries use parameterized prepared statements (`%s` placeholders).
- **Password Security:** Scrypt/PBKDF2 one-way salted password hashing.

### 6.2 Test Results
The automated test suite in `tests/` executed 20 test cases with **100% pass rate**:
- Authentication & accounts: 6 tests (Valid admin/owner, invalid password, nonexistent email, registration, duplicate rejection)
- Booking & collisions: 5 tests (Valid booking, overlapping collision rejection, invalid date ranges, unowned vehicle check, cancellation)
- Role boundaries & IDOR: 6 tests (Anonymous redirection, owner blocked from admin routes, admin blocked from owner routes, IDOR vehicle deletion prevention, IDOR booking cancellation prevention, atomic transaction rollback)
- Session lifecycle & payments: 3 tests (Stored procedure execution, negative energy rejection, duplicate payment reference rejection)

---

## 7. Phase 5: Web Integration & User Experience

The application is deployed on `http://127.0.0.1:5000` with:
- **Admin Portal:** Live dashboard KPIs, station manager, charging dispenser hardware config, per-kWh tariff tuning, reservations overview, sessions log, payments ledger, and analytical reports.
- **EV Owner Portal:** Personalized dashboard, vehicle profile registration, station search by city, time-slot reservation with real-time collision detection, live interactive charging session simulator (accumulating kWh, duration timer, live cost), and payment settlement with instant receipts.

---

## 8. Conclusion

The EV Charging Station Management System satisfies all requirements across all five capstone phases. The project demonstrates rigorous database design, procedural SQL programming, performance indexing, enterprise security, and end-to-end integration into a cohesive, production-grade application.
