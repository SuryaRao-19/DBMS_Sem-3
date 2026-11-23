# RELATIONAL DATABASE DATA DICTIONARY
## EV Charging Station Management System — Major Upgrade 2.0
**Target Database:** `ev_charging_db` on MySQL 8.0+ (InnoDB)  
**File:** `docs/data_dictionary.md`

---

## 1. Schema Overview

The database `ev_charging_db` comprises **9 relational tables** normalized to **Third Normal Form (3NF)**. All tables use the **InnoDB** storage engine to guarantee ACID transactions, foreign key constraints, and row-level locking.

Character Set: `utf8mb4` | Collation: `utf8mb4_unicode_ci`

---

## 2. Table-by-Table Data Dictionary

### 2.1 `Users` Table
**Purpose:** Central repository for user accounts, credentials, contact information, and role-based access control.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `user_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique surrogate identifier for each user account. |
| `full_name` | `VARCHAR(100)` | NO | | None | Non-empty | User's legal or registered name. |
| `email` | `VARCHAR(120)` | NO | **UNI** | None | Unique Email | Login identifier and primary communication channel. |
| `phone` | `VARCHAR(20)` | YES | | None | Standard format | Mobile contact number for OTP or notifications. |
| `password_hash` | `VARCHAR(255)` | NO | | None | Cryptographic | Secure scrypt/PBKDF2 salted hash string. |
| `role` | `ENUM('ADMIN','OWNER')`| NO | | `'OWNER'` | ENUM Check | System authorization role (`ADMIN` or `OWNER`). |
| `account_status`| `ENUM('ACTIVE','INACTIVE')`| NO | | `'ACTIVE'` | ENUM Check | Operational account status (enables admin suspension). |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Account registration timestamp. |

---

### 2.2 `Vehicles` Table
**Purpose:** Electric vehicles registered by EV owners to reserve compatible charging dispensers.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `vehicle_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique surrogate identifier for each vehicle. |
| `user_id` | `INT` | NO | **FK** | None | `REFERENCES Users(user_id) ON DELETE CASCADE` | Foreign key identifying the registered owner. |
| `registration_no`| `VARCHAR(30)` | NO | **UNI** | None | Unique Identifier | Official vehicle license plate registration number. |
| `make` | `VARCHAR(60)` | NO | | None | Non-empty | Vehicle manufacturer (e.g. Tata, MG, Hyundai). |
| `model` | `VARCHAR(60)` | NO | | None | Non-empty | Vehicle model name (e.g. Nexon EV, ZS EV). |
| `battery_capacity_kwh`| `DECIMAL(8,2)`| NO | | None | `CHECK (battery_capacity_kwh > 0)` | Total usable battery capacity in kilowatt-hours. |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Vehicle registration timestamp. |

---

### 2.3 `Stations` Table
**Purpose:** Physical charging locations/hubs housing one or more charging dispensers.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `station_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique surrogate identifier for each charging station. |
| `station_name` | `VARCHAR(120)` | NO | | None | Non-empty | Public facility or brand name of the charging hub. |
| `address` | `VARCHAR(255)` | NO | | None | Non-empty | Physical street address of the charging station. |
| `city` | `VARCHAR(80)` | NO | **IDX** | None | Non-empty | Metropolitan city or district for geographical filtering. |
| `opening_time` | `TIME` | YES | | None | HH:MM:SS | Daily operational opening time. |
| `closing_time` | `TIME` | YES | | None | HH:MM:SS | Daily operational closing time. |
| `station_status`| `ENUM('ACTIVE','INACTIVE','MAINTENANCE')`| NO | **IDX** | `'ACTIVE'` | ENUM Check | Facility operational availability. |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Station commissioning timestamp. |

---

### 2.4 `ChargingPoints` Table
**Purpose:** Individual dispensers located at a charging station with specific connector types and tariffs.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `point_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique surrogate identifier for each dispenser. |
| `station_id` | `INT` | NO | **FK** | None | `REFERENCES Stations(station_id) ON DELETE CASCADE` | Parent charging station ID. |
| `point_code` | `VARCHAR(30)` | NO | **UNI** | None | Unique per station | Bay / dispenser code label (e.g. 'CP-01'). |
| `connector_type`| `ENUM('TYPE2','CCS2','CHADEMO','GB_T')`| NO | | None | Standardized ENUM | Standard physical connector protocol. |
| `max_power_kw` | `DECIMAL(8,2)` | NO | | None | `CHECK (max_power_kw > 0)` | Maximum power delivery rating in kW. |
| `tariff_per_kwh`| `DECIMAL(10,2)`| NO | | None | `CHECK (tariff_per_kwh >= 0)` | Energy billing rate in INR per kilowatt-hour. |
| `point_status` | `ENUM('AVAILABLE','OCCUPIED','UNAVAILABLE','MAINTENANCE')`| NO | **IDX** | `'AVAILABLE'` | Real-time state | Real-time operational dispenser status. |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Point provisioning timestamp. |

---

### 2.5 `Bookings` Table
**Purpose:** Reservation intervals booked by EV owners for a specific charging point.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `booking_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique reservation reference number. |
| `user_id` | `INT` | NO | **FK** | None | `REFERENCES Users(user_id) ON DELETE RESTRICT` | Booking driver ID. |
| `vehicle_id` | `INT` | NO | **FK** | None | `REFERENCES Vehicles(vehicle_id) ON DELETE RESTRICT` | Vehicle assigned to reservation. |
| `point_id` | `INT` | NO | **FK** | None | `REFERENCES ChargingPoints(point_id) ON DELETE RESTRICT` | Reserved charging dispenser. |
| `start_at` | `DATETIME` | NO | **IDX** | None | Future datetime | Scheduled reservation start time. |
| `end_at` | `DATETIME` | NO | **IDX** | None | `CHECK (end_at > start_at)` | Scheduled reservation end time. |
| `booking_status`| `ENUM('PENDING','CONFIRMED','CANCELLED','COMPLETED')`| NO | **IDX** | `'PENDING'` | Lifecycle ENUM | Status: `PENDING`, `CONFIRMED`, `CANCELLED`, `COMPLETED`. |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Reservation placement timestamp. |

---

### 2.6 `ChargingSessions` Table
**Purpose:** Actual charging events recording energy dispensed and computing total billing charges.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `session_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique charging session identifier. |
| `booking_id` | `INT` | YES | **UNI** | None | `REFERENCES Bookings(booking_id) ON DELETE RESTRICT` | Associated reservation booking ID (1:1). |
| `user_id` | `INT` | NO | **FK** | None | `REFERENCES Users(user_id) ON DELETE RESTRICT` | EV driver being billed. |
| `vehicle_id` | `INT` | NO | **FK** | None | `REFERENCES Vehicles(vehicle_id) ON DELETE RESTRICT` | Vehicle connected to dispenser. |
| `point_id` | `INT` | NO | **FK** | None | `REFERENCES ChargingPoints(point_id) ON DELETE RESTRICT` | Dispenser delivering electricity. |
| `start_at` | `DATETIME` | NO | **IDX** | None | Session initiation | Session start timestamp. |
| `end_at` | `DATETIME` | YES | | None | `CHECK (end_at >= start_at)` | Session termination timestamp. |
| `energy_kwh` | `DECIMAL(10,3)`| NO | | `0.000` | `CHECK (energy_kwh >= 0)` | Metered energy delivered to vehicle (kWh). |
| `tariff_per_kwh`| `DECIMAL(10,2)`| NO | | None | Rate snapshot | Applied tariff snapshot per kWh (INR). |
| `total_cost` | `DECIMAL(12,2)`| NO | | `0.00` | `CHECK (total_cost >= 0)` | Computed financial charge (`energy * tariff`). |
| `session_status`| `ENUM('IN_PROGRESS','COMPLETED','CANCELLED')`| NO | | `'IN_PROGRESS'` | Session Lifecycle | Operational status of charging cycle. |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Session creation timestamp. |

---

### 2.7 `Payments` Table
**Purpose:** Financial ledger recording settlements linked to charging sessions.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `payment_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique ledger payment identifier. |
| `session_id` | `INT` | NO | **FK** | None | `REFERENCES ChargingSessions(session_id) ON DELETE RESTRICT` | Billed session reference. |
| `transaction_reference`| `VARCHAR(100)`| NO | **UNI** | None | Unique string | Unique financial receipt / transaction reference. |
| `amount` | `DECIMAL(12,2)`| NO | | None | `CHECK (amount >= 0)` | Total settled monetary amount (INR). |
| `payment_method`| `ENUM('UPI','CARD','CASH','WALLET')`| NO | | None | Payment channel | Method used for settlement. |
| `payment_status`| `ENUM('PENDING','SUCCESS','FAILED','REFUNDED')`| NO | **IDX** | `'PENDING'` | Financial state | State: `SUCCESS`, `PENDING`, `FAILED`, `REFUNDED`. |
| `paid_at` | `DATETIME` | YES | **IDX** | None | Settlement time | Settlement timestamp. |
| `created_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP` | System Time | Payment creation timestamp. |

---

### 2.8 `AuditLogs` Table
**Purpose:** Immutable administrative event log capturing privileged operations.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `log_id` | `INT` | NO | **PK** | `AUTO_INCREMENT` | Positive Integer | Unique audit event log sequence number. |
| `user_id` | `INT` | YES | **FK** | `NULL` | `REFERENCES Users(user_id) ON DELETE SET NULL` | Administrator performing the action. |
| `action` | `VARCHAR(80)` | NO | | None | Action verb | Event name (e.g. `CREATE_STATION`, `UPDATE_TARIFF`). |
| `entity_name` | `VARCHAR(50)` | NO | **IDX** | None | Table name | Database entity affected. |
| `entity_id` | `INT` | YES | **IDX** | `NULL` | Target ID | Primary key of affected record. |
| `details` | `TEXT` | YES | | `NULL` | Free text / JSON | Detailed description of modifications made. |
| `ip_address` | `VARCHAR(45)` | YES | | `NULL` | IPv4 / IPv6 | Client IP address of requesting user. |
| `created_at` | `TIMESTAMP` | NO | **IDX** | `CURRENT_TIMESTAMP` | Audit Timestamp | Timestamp when the event occurred. |

---

### 2.9 `SystemSettings` Table
**Purpose:** Configurable application parameters managed dynamically through the database.

| Column Name | Data Type | Nullable | Key | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `setting_key` | `VARCHAR(50)` | NO | **PK** | None | Alphanumeric Key | Unique configuration identifier (e.g. `tax_rate_percent`). |
| `setting_value` | `VARCHAR(255)`| NO | | None | String / Numeric | Active setting value. |
| `description` | `VARCHAR(255)`| YES | | `NULL` | Description text | Human-readable explanation of the setting. |
| `updated_at` | `TIMESTAMP` | NO | | `CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | Auto-update | Last modification timestamp. |
