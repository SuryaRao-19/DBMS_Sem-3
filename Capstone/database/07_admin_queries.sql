-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 7: ADMINISTRATIVE TOOLKIT
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/07_admin_queries.sql
-- Description: Practical, commented SQL commands for database inspection,
--              record querying, safe transaction modifications, and troubleshooting.
-- ============================================================

USE ev_charging_db;

-- ============================================================
-- SECTION A: DATABASE INSPECTION COMMANDS
-- ============================================================

-- 1. List all databases on server
SHOW DATABASES;

-- 2. Confirm selection of target schema
SELECT DATABASE() AS active_schema;

-- 3. List all tables and views in ev_charging_db
SHOW FULL TABLES;

-- 4. Inspect table schema, nullability, default values, and keys
DESCRIBE Users;
DESCRIBE Vehicles;
DESCRIBE Bookings;
DESCRIBE ChargingSessions;
DESCRIBE Payments;
DESCRIBE AuditLogs;
DESCRIBE SystemSettings;

-- 5. View exact SQL CREATE TABLE statement including constraints and engine
SHOW CREATE TABLE Bookings;
SHOW CREATE TABLE ChargingSessions;

-- 6. List all B-Tree indexes on Bookings table
SHOW INDEX FROM Bookings;

-- 7. Inspect database triggers and stored routines
SHOW TRIGGERS FROM ev_charging_db;
SHOW PROCEDURE STATUS WHERE Db = 'ev_charging_db';
SHOW FUNCTION STATUS WHERE Db = 'ev_charging_db';

-- 8. Advanced schema inspection via INFORMATION_SCHEMA
SELECT 
    TABLE_NAME, 
    COLUMN_NAME, 
    DATA_TYPE, 
    IS_NULLABLE, 
    COLUMN_KEY, 
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ev_charging_db' AND TABLE_NAME = 'ChargingPoints';

-- ============================================================
-- SECTION B: VIEW AND QUERY RECORDS (MULTI-TABLE JOINS)
-- ============================================================

-- 1. View all stations with live dispenser counts
SELECT 
    s.station_id,
    s.station_name,
    s.city,
    s.station_status,
    COUNT(cp.point_id) AS total_points
FROM Stations s
LEFT JOIN ChargingPoints cp ON s.station_id = cp.station_id
GROUP BY s.station_id, s.station_name, s.city, s.station_status;

-- 2. View all charging points grouped with parent station
SELECT 
    cp.point_id,
    s.station_name,
    s.city,
    cp.point_code,
    cp.connector_type,
    cp.max_power_kw,
    cp.tariff_per_kwh,
    cp.point_status
FROM ChargingPoints cp
JOIN Stations s ON cp.station_id = s.station_id
ORDER BY s.station_name, cp.point_code;

-- 3. Find vehicles owned by a specific customer (e.g. user_id = 2)
SELECT 
    u.full_name AS owner_name,
    u.email,
    v.vehicle_id,
    v.registration_no,
    v.make,
    v.model,
    v.battery_capacity_kwh
FROM Vehicles v
JOIN Users u ON v.user_id = u.user_id
WHERE u.user_id = 2;

-- 4. Comprehensive booking registry with customer, vehicle, station, and point
SELECT 
    b.booking_id,
    u.full_name AS customer_name,
    u.phone AS customer_phone,
    v.registration_no,
    CONCAT(v.make, ' ', v.model) AS vehicle_name,
    s.station_name,
    cp.point_code,
    cp.connector_type,
    b.start_at,
    b.end_at,
    b.booking_status
FROM Bookings b
JOIN Users u ON b.user_id = u.user_id
JOIN Vehicles v ON b.vehicle_id = v.vehicle_id
JOIN ChargingPoints cp ON b.point_id = cp.point_id
JOIN Stations s ON cp.station_id = s.station_id
ORDER BY b.start_at DESC;

-- 5. View complete charging session ledger with payments
SELECT 
    cs.session_id,
    cs.booking_id,
    u.full_name AS customer_name,
    s.station_name,
    cp.point_code,
    cs.start_at,
    cs.end_at,
    cs.energy_kwh,
    cs.total_cost,
    cs.session_status,
    p.transaction_reference,
    p.amount AS amount_paid,
    p.payment_status
FROM ChargingSessions cs
JOIN Users u ON cs.user_id = u.user_id
JOIN ChargingPoints cp ON cs.point_id = cp.point_id
JOIN Stations s ON cp.station_id = s.station_id
LEFT JOIN Payments p ON cs.session_id = p.session_id
ORDER BY cs.start_at DESC;

-- ============================================================
-- SECTION C: SAFELY MODIFY RECORDS (TRANSACTION TEMPLATES)
-- ============================================================

-- Example 1: Add a new station and associated dispenser safely
START TRANSACTION;

INSERT INTO Stations (station_name, address, city, opening_time, closing_time, station_status)
VALUES ('South Extension Supercharge', 'Ring Road, South Ext Part II', 'New Delhi', '06:00:00', '23:00:00', 'ACTIVE');

SET @new_station_id = LAST_INSERT_ID();

INSERT INTO ChargingPoints (station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
VALUES (@new_station_id, 'CP-01', 'CCS2', 60.00, 19.00, 'AVAILABLE');

-- Inspect changes before committing
SELECT * FROM Stations WHERE station_id = @new_station_id;
SELECT * FROM ChargingPoints WHERE station_id = @new_station_id;

-- If satisfied, commit:
COMMIT;
-- If any error occurred, rollback instead:
-- ROLLBACK;

-- Example 2: Update charging point tariff with an audit log entry
START TRANSACTION;

UPDATE ChargingPoints
SET tariff_per_kwh = 21.00
WHERE point_id = 1;

INSERT INTO AuditLogs (user_id, action, entity_name, entity_id, details)
VALUES (1, 'UPDATE_TARIFF', 'ChargingPoints', 1, 'Updated CP-01 tariff to 21.00 INR/kWh');

COMMIT;

-- Example 3: Cancel an eligible booking safely
START TRANSACTION;

SELECT booking_id, booking_status, start_at
FROM Bookings
WHERE booking_id = 7
FOR UPDATE;

UPDATE Bookings
SET booking_status = 'CANCELLED'
WHERE booking_id = 7 AND booking_status IN ('PENDING', 'CONFIRMED');

INSERT INTO AuditLogs (user_id, action, entity_name, entity_id, details)
VALUES (1, 'CANCEL_BOOKING', 'Bookings', 7, 'Administrative cancellation of booking #7');

COMMIT;

-- ============================================================
-- SECTION D: DATABASE TROUBLESHOOTING & DIAGNOSTICS
-- ============================================================

-- 1. Inspect currently running threads and queries
SHOW PROCESSLIST;

-- 2. Deep diagnostic status of InnoDB engine (includes latest deadlock info)
SHOW ENGINE INNODB STATUS;

-- 3. Check for lock waits and concurrency contention (MySQL 8+ Performance Schema)
SELECT 
    r.trx_id waiting_trx_id,
    r.trx_mysql_thread_id waiting_thread,
    r.trx_query waiting_query,
    b.trx_id blocking_trx_id,
    b.trx_mysql_thread_id blocking_thread,
    b.trx_query blocking_query
FROM performance_schema.data_lock_waits w
JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_engine_transaction_id
JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_engine_transaction_id;

-- 4. Check active character sets and collations
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

-- 5. Identify any potential data anomalies (e.g. point marked OCCUPIED without active session)
SELECT cp.point_id, cp.point_code, cp.point_status, s.station_name
FROM ChargingPoints cp
JOIN Stations s ON cp.station_id = s.station_id
WHERE cp.point_status = 'OCCUPIED'
  AND cp.point_id NOT IN (
      SELECT point_id FROM ChargingSessions WHERE session_status = 'IN_PROGRESS'
  );
