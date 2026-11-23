# EV Charging Station Management System: Relational Schema & 3NF Normalization

**Course:** Database Management Systems (DBMS) Capstone Project  
**Target RDBMS:** MySQL 8.0+ (InnoDB Storage Engine)  
**Deliverable:** Phase 1 Design Specification  

---

## 1. Domain Overview & Enterprise Requirements

The **EV Charging Station Management System** manages electric vehicle charging infrastructure, customer vehicle profiles, time-slot reservations, real-time energy dispensing sessions, and financial settlements.

The core entities comprise:
1. **Users:** Account management and role-based access control (`ADMIN` vs `OWNER`).
2. **Vehicles:** EV registry owned by users with battery capacity metrics.
3. **Stations:** Physical charging depots situated in distinct geographic regions with defined operating schedules.
4. **ChargingPoints:** Individual dispensers/chargers located within stations, specifying connector standards (`CCS2`, `TYPE2`, `CHADEMO`, `GB_T`), maximum power ratings (kW), and live availability.
5. **Bookings:** Advance reservations ensuring zero slot contention.
6. **ChargingSessions:** Operational telemetry tracking energy delivered ($kWh$), billing rates, session timestamps, and operational status.
7. **Payments:** Audit-compliant financial records capturing payment mode, reconciliation reference, and settlement state.

---

## 2. Relational Schema Specification

### 2.1 Users
`Users (user_id [PK], full_name, email [UK], phone, password_hash, role, account_status, created_at)`
- **Primary Key:** `user_id` (INT AUTO_INCREMENT)
- **Alternate/Candidate Key:** `email` (VARCHAR(120) UNIQUE)
- **Constraints:** 
  - `role IN ('ADMIN', 'OWNER')`
  - `account_status IN ('ACTIVE', 'INACTIVE')`
  - `email`, `full_name`, `password_hash` NOT NULL

### 2.2 Vehicles
`Vehicles (vehicle_id [PK], user_id [FK], registration_no [UK], make, model, battery_capacity_kwh, created_at)`
- **Primary Key:** `vehicle_id` (INT AUTO_INCREMENT)
- **Candidate Key:** `registration_no` (VARCHAR(30) UNIQUE)
- **Foreign Key:** `user_id REFERENCES Users(user_id) ON DELETE CASCADE`
- **Domain Constraints:** `CHECK (battery_capacity_kwh > 0)`

### 2.3 Stations
`Stations (station_id [PK], station_name, address, city, opening_time, closing_time, station_status, created_at)`
- **Primary Key:** `station_id` (INT AUTO_INCREMENT)
- **Constraints:** `station_status IN ('ACTIVE', 'INACTIVE', 'MAINTENANCE')`

### 2.4 ChargingPoints
`ChargingPoints (point_id [PK], station_id [FK], point_code, connector_type, max_power_kw, tariff_per_kwh, point_status, created_at)`
- **Primary Key:** `point_id` (INT AUTO_INCREMENT)
- **Composite Candidate Key:** `(station_id, point_code) UNIQUE`
- **Foreign Key:** `station_id REFERENCES Stations(station_id) ON DELETE CASCADE`
- **Domain Constraints:**
  - `connector_type IN ('TYPE2', 'CCS2', 'CHADEMO', 'GB_T')`
  - `point_status IN ('AVAILABLE', 'OCCUPIED', 'UNAVAILABLE', 'MAINTENANCE')`
  - `CHECK (max_power_kw > 0)`
  - `CHECK (tariff_per_kwh >= 0)`

### 2.5 Bookings
`Bookings (booking_id [PK], user_id [FK], vehicle_id [FK], point_id [FK], start_at, end_at, booking_status, created_at)`
- **Primary Key:** `booking_id` (INT AUTO_INCREMENT)
- **Foreign Keys:**
  - `user_id REFERENCES Users(user_id)`
  - `vehicle_id REFERENCES Vehicles(vehicle_id)`
  - `point_id REFERENCES ChargingPoints(point_id)`
- **Domain Constraints:**
  - `CHECK (end_at > start_at)`
  - `booking_status IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED')`
- **Indexes:** `(point_id, start_at, end_at)`, `(user_id, booking_status)`

### 2.6 ChargingSessions
`ChargingSessions (session_id [PK], booking_id [FK, UK], user_id [FK], vehicle_id [FK], point_id [FK], start_at, end_at, energy_kwh, tariff_per_kwh, total_cost, session_status, created_at)`
- **Primary Key:** `session_id` (INT AUTO_INCREMENT)
- **Foreign Keys:**
  - `booking_id REFERENCES Bookings(booking_id)` (Unique, Nullable for walk-ins)
  - `user_id REFERENCES Users(user_id)`
  - `vehicle_id REFERENCES Vehicles(vehicle_id)`
  - `point_id REFERENCES ChargingPoints(point_id)`
- **Domain Constraints:**
  - `CHECK (energy_kwh >= 0)`
  - `CHECK (tariff_per_kwh >= 0)`
  - `CHECK (total_cost >= 0)`
  - `CHECK (end_at IS NULL OR end_at >= start_at)`
  - `session_status IN ('IN_PROGRESS', 'COMPLETED', 'CANCELLED')`

### 2.7 Payments
`Payments (payment_id [PK], session_id [FK], transaction_reference [UK], amount, payment_method, payment_status, paid_at, created_at)`
- **Primary Key:** `payment_id` (INT AUTO_INCREMENT)
- **Candidate Key:** `transaction_reference UNIQUE`
- **Foreign Key:** `session_id REFERENCES ChargingSessions(session_id)`
- **Domain Constraints:**
  - `amount >= 0`
  - `payment_method IN ('UPI', 'CARD', 'CASH', 'WALLET')`
  - `payment_status IN ('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED')`

---

## 3. Normalization Justification (1NF to 3NF)

### 3.1 First Normal Form (1NF)
A relation is in 1NF if and only if:
1. Every attribute domain contains only atomic (indivisible) values.
2. There are no repeating groups or multivalued arrays.
3. Each record is uniquely identifiable via a Primary Key.

**Verification:**
- In `Users`, attributes such as `phone`, `email`, and `full_name` contain atomic scalar literals.
- In `ChargingPoints`, `connector_type` stores a single standard per dispenser record. Multi-gun dispensers are modeled as separate distinct records (`CP-01`, `CP-02`) sharing a `station_id`.
- In `ChargingSessions` and `Payments`, timestamps and numeric costs/amounts use explicit atomic types (`DATETIME`, `DECIMAL(12,2)`).

### 3.2 Second Normal Form (2NF)
A relation is in 2NF if and only if:
1. It is in 1NF.
2. No non-prime attribute is functionally dependent on a proper subset of any candidate key (i.e., **No Partial Dependencies**).

**Verification:**
- For relations with single-attribute primary keys (`Users`, `Vehicles`, `Stations`, `Bookings`, `ChargingSessions`, `Payments`), partial key dependencies are mathematically impossible.
- For `ChargingPoints`, the composite candidate key is `(station_id, point_code)`:
  - Functional dependencies:
    - `{point_id} -> {station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status}`
    - `{station_id, point_code} -> {point_id, connector_type, max_power_kw, tariff_per_kwh, point_status}`
  - Non-key attributes (`connector_type`, `max_power_kw`, `tariff_per_kwh`, `point_status`) describe the individual dispenser in that station and depend on the **entire composite key**, not on `station_id` alone. Station-level attributes (`address`, `city`) are separated into the `Stations` relation.
- Therefore, the schema is strictly in 2NF.

### 3.3 Third Normal Form (3NF)
A relation is in 3NF if and only if:
1. It is in 2NF.
2. For every non-trivial functional dependency $X \rightarrow Y$, either:
   - $X$ is a superkey, OR
   - $Y$ is a prime attribute (member of a candidate key).
   (i.e., **No Transitive Dependencies** among non-key attributes).

**Verification across all tables:**
- **Users:** Non-key attributes (`full_name`, `phone`, `role`) depend directly on `user_id` (superkey). No non-key attribute determines another non-key attribute.
- **Vehicles:** `user_id`, `make`, `model`, `battery_capacity_kwh` depend directly on `vehicle_id`. An EV's battery capacity is vehicle-specific and depends on `vehicle_id`.
- **Stations:** `station_name`, `address`, `city` depend on `station_id`. Cities do not determine stations.
- **ChargingPoints:** Station attributes (`station_name`, `city`) are **not** duplicated here; only the foreign key `station_id` is stored.
- **Bookings:** Does not store user names, vehicle license plates, or station names; only foreign keys (`user_id`, `vehicle_id`, `point_id`) are stored.
- **ChargingSessions:** 
  - Why store `tariff_per_kwh` and `total_cost`?
    * `tariff_per_kwh` in `ChargingSessions` represents the **historical tariff locked at the moment of charging**, protecting historical financial records from future price adjustments on the charging point.
    * `total_cost` is calculated via deterministic stored logic ($energy\_kwh \times tariff\_per\_kwh$) and persisted for immutable financial audit trails and ledger reconciliation.
- **Payments:** `session_id`, `amount`, `payment_method`, and `payment_status` depend strictly on `payment_id` and `transaction_reference`.

---

## 4. Referential Integrity Rules

| Foreign Key | Parent Table | Child Table | On Delete | On Update | Rationale |
|---|---|---|---|---|---|
| `user_id` | `Users` | `Vehicles` | `CASCADE` | `CASCADE` | Deleting an owner account removes their registered vehicle profiles. |
| `station_id` | `Stations` | `ChargingPoints` | `CASCADE` | `CASCADE` | Decommissioning a station safely removes its child dispensers. |
| `user_id` | `Users` | `Bookings` | `RESTRICT` | `CASCADE` | Historical reservations cannot be purged if audit trails exist. |
| `point_id` | `ChargingPoints` | `Bookings` | `RESTRICT` | `CASCADE` | Active booking history is preserved. |
| `booking_id` | `Bookings` | `ChargingSessions` | `SET NULL` | `CASCADE` | Sessions remain intact for revenue accounting if a booking record is pruned. |
| `session_id` | `ChargingSessions` | `Payments` | `RESTRICT` | `CASCADE` | Financial ledgers cannot be deleted while session records exist. |

---

## 5. Business Rules & Concurrency Handling

1. **Overlap Prevention Constraint:**
   Two bookings for the same `point_id` cannot overlap if both are in `PENDING` or `CONFIRMED` status.
   Interval overlap condition:
   $$\text{NEW.start\_at} < \text{existing.end\_at} \quad \text{AND} \quad \text{NEW.end\_at} > \text{existing.start\_at}$$
   Enforced via database trigger `trg_booking_before_insert` and verified at backend API level.

2. **Session Lifecycle & State Machine:**
   - Active: `IN_PROGRESS`
   - Complete: `COMPLETED`
   - Cancel: `CANCELLED`
   Completion is governed by stored procedure `CompleteChargingSession`, which applies row-level locking (`SELECT ... FOR UPDATE`), calculates total bill, marks session completed, and restores point availability to `AVAILABLE` atomically within a single ACID transaction.

3. **Deterministic Financial Precision:**
   All monetary amounts use `DECIMAL(12,2)` and energy quantities use `DECIMAL(10,3)` to prevent IEEE 754 floating-point rounding errors.
