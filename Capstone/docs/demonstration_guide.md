# EV Charging Station Management System: 5–7 Minute Demonstration Guide

**Project:** DBMS Capstone Project (100 Marks)  
**Target Audience:** Project Evaluators, External Examiners, and DBMS Faculty  
**System URL:** `http://127.0.0.1:5000`  

---

## 1. Demo Credentials Quick Reference

| Role | Email | Password | Access Rights |
|---|---|---|---|
| **Station Administrator** | `admin@evdemo.com` | `Admin@123` | Full infrastructure management, points, tariffs, operational reports |
| **EV Owner (Driver)** | `aarav@example.com` | `Owner@123` | Vehicle management, station browsing, slot reservation, live charging, receipts |

---

## 2. Minute-by-Minute Demonstration Sequence

### Minute 0:00 – 1:00 | Architecture & Schema Justification
1. **Explain the Domain:** Electric Vehicle charging infrastructure management, resolving slot contention, monitoring energy dispensed, and handling billing settlements.
2. **Highlight the DBMS Rigor:**
   - Database normalized strictly to **Third Normal Form (3NF)**.
   - ACID-compliant transactions with `START TRANSACTION`, `FOR UPDATE` row locking, and rollback handlers.
   - Triggers for domain validation (`trg_booking_before_insert`, `trg_session_before_insert`).
   - Procedural SQL (`CalculateChargingCost`, `CompleteChargingSession`).

---

### Minute 1:00 – 2:30 | Administrator Journey (Infrastructure & Reports)
1. **Log in as Admin:**
   - Go to `http://127.0.0.1:5000/login`.
   - Click the **"👤 Admin"** quick-fill button, then click **Sign In**.
2. **Review Executive Dashboard (`/admin/dashboard`):**
   - Point out the 4 primary KPI cards: **Total Stations (3)**, **Charging Dispensers (6)**, **Energy Dispensed (140.0 kWh)**, and **Total Revenue (₹2,416.00)**.
   - Explain that all numbers are computed via SQL aggregation (`SUM`, `COUNT`, `GROUP BY`) from live database tables—zero hardcoded mock data.
3. **Configure Charging Points & Tariffs (`/admin/points`):**
   - Click **Dispensers** in the navbar.
   - Demonstrate the **"Configure Tariff"** button on dispenser `CP-01` at Connaught Place Hub.
   - Show how changing the per-kWh tariff updates the database in real-time.
4. **Examine Phase 3 Reports (`/admin/reports`):**
   - Show **Report 1: Monthly Revenue by Station**.
   - Show **Report 2: Monthly Energy Dispensed**.
   - Show **Report 3: Station Utilization** (Hours delivered).
   - Show **Report 4: Booking Status Distribution** with visual share bars.

---

### Minute 2:30 – 4:30 | EV Owner Journey (Booking, Charging & Payment)
1. **Switch to EV Owner:**
   - Click **Log Out** in the navigation bar.
   - Click the **"🚗 EV Owner"** quick-fill button (`aarav@example.com` / `Owner@123`) and log in.
2. **Vehicle Management (`/owner/vehicles`):**
   - Show registered vehicle: *Tata Nexon EV (DL01EV1001)* with 40.50 kWh battery pack.
3. **Browse Stations & Reserve Slot (`/owner/stations`):**
   - Filter stations by city: type `New Delhi` and press filter.
   - Click **"Book Slot"** on dispenser `CP-01` (CCS2 - 60 kW).
   - The booking form opens with an automated conflict detection check.
   - Select a valid time slot and click **Confirm Slot Reservation**.
   - Verify the reservation appears under **My Reservations**.
4. **Live Charging Simulator (`/owner/charging`):**
   - Click **⚡ Live Charging** in the navbar.
   - Click **⚡ Start Charging Session**.
   - **Show the Live Meter:** The display starts ticking, showing real-time accumulating kWh (e.g. `12.450 kWh`), session timer (`00:02:15`), and live estimated cost in ₹ based on the station's tariff!
   - Explain that the charging point status in the database has atomically transitioned to `OCCUPIED`.
5. **Complete Charging & Instant Payment:**
   - Click **⏹ Stop Charging & Generate Bill**.
   - Explain that this triggers the MySQL Stored Procedure `CompleteChargingSession(session_id, energy_kwh)`:
     * Validates session is `IN_PROGRESS`.
     * Calculates cost using deterministic function `CalculateChargingCost(kWh, Tariff)`.
     * Marks session `COMPLETED`.
     * Restores dispenser state back to `AVAILABLE`.
   - The payment modal opens with the exact calculated amount (e.g., ₹224.00).
   - Select **UPI** and click **Authorize Simulated Payment**.
   - System confirms settlement with unique transaction reference `EVTXN-XXXXXXXX`!

---

### Minute 4:30 – 5:30 | Security & Concurrency Verification
1. **Demonstrate Overlapping Slot Rejection:**
   - Try to book the exact same dispenser and time slot as an existing reservation.
   - System displays the error banner: *"Conflict: Another confirmed reservation exists during this window."*
   - Explain that this is enforced both at the application level and by the database trigger `trg_booking_before_insert`.
2. **Demonstrate Role Boundary Enforcement:**
   - As an EV owner, manually navigate to `http://127.0.0.1:5000/admin/dashboard`.
   - The server rejects access with **HTTP 403 Forbidden** (access denied error page).
3. **Demonstrate IDOR Security:**
   - Explain that user IDs are strictly retrieved from authenticated session tokens on the server, never from client-supplied URL parameters or form inputs.

---

### Minute 5:30 – 7:00 | Database Mechanics & Viva Q&A
1. **Show Query Plan Optimization (`docs/query_plan_comparison.md`):**
   - Show how adding the composite B-Tree index `idx_payment_status_date (payment_status, paid_at)` converted a full table scan (`type: ALL`) into an index range scan (`type: range`), reducing disk I/O.
2. **Highlight the Test Suite:**
   - Point to `pytest` results showing **20 passed in 13.83s** across authentication, slot conflicts, stored procedures, constraints, and transactions.

---

## 3. Top Viva Questions & Model Answers

### Q1: Why is this database design in 3NF?
**Answer:**  
In all 7 tables, every non-key attribute depends directly on the primary key (no partial dependencies $\rightarrow$ 2NF) and on nothing else (no transitive dependencies between non-key attributes $\rightarrow$ 3NF). For example, charging point tables only store `station_id` (foreign key) rather than duplicating station addresses or cities. Historical tariffs in `ChargingSessions` are stored to protect financial audits from future tariff changes, which is a recognized temporal design pattern in transactional DBMS.

### Q2: How does the system handle booking slot conflicts?
**Answer:**  
Conflict detection uses the interval overlap formula:
$$(\text{NEW.start\_at} < \text{existing.end\_at}) \quad \text{AND} \quad (\text{NEW.end\_at} > \text{existing.start\_at})$$
This is validated before submission and strictly enforced inside the database by the `BEFORE INSERT` trigger `trg_booking_before_insert`, which executes a `SIGNAL SQLSTATE '45000'` if `conflict_count > 0`, rolling back any invalid reservation attempt.

### Q3: Why use a Stored Procedure for session completion instead of an application query?
**Answer:**  
`CompleteChargingSession` executes multiple interdependent operations atomically:
1. Locks the session record with `SELECT ... FOR UPDATE` to avoid race conditions.
2. Calls the deterministic stored function `CalculateChargingCost`.
3. Updates `ChargingSessions` end timestamp, energy, and total bill.
4. Restores `ChargingPoints` status to `AVAILABLE`.
5. Employs `DECLARE EXIT HANDLER FOR SQLEXCEPTION` with `ROLLBACK` to guarantee ACID atomicity even if the server crashes mid-execution.

### Q4: What did the EXPLAIN analysis prove?
**Answer:**  
Running `EXPLAIN` on `Payments` before indexing showed access type `ALL` (full table scan) with `Using where`. After creating the composite B-Tree index `(payment_status, paid_at)`, the optimizer switched to `range` scan using `Index Condition Pushdown (ICP)`, drastically reducing page I/O from $O(N)$ to $O(\log N + K)$.
