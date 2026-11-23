-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 5: DATABASE VERIFICATION SUITE
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/05_verification.sql
-- Description: Automated SQL verification checking schema presence,
--              record counts, foreign key integrity, routines, triggers,
--              and constraint enforcement.
-- ============================================================

USE ev_charging_db;

-- ------------------------------------------------------------
-- TEST 1: DATABASE ENVIRONMENT & STORAGE ENGINE
-- ------------------------------------------------------------
SELECT 
    DATABASE() AS current_database,
    VERSION() AS mysql_version,
    @@character_set_database AS default_charset,
    @@collation_database AS default_collation;

-- ------------------------------------------------------------
-- TEST 2: CORE TABLE INVENTORY & EXACT ROW COUNTS
-- ------------------------------------------------------------
SELECT 'Users' AS table_name, COUNT(*) AS record_count FROM Users
UNION ALL
SELECT 'Vehicles', COUNT(*) FROM Vehicles
UNION ALL
SELECT 'Stations', COUNT(*) FROM Stations
UNION ALL
SELECT 'ChargingPoints', COUNT(*) FROM ChargingPoints
UNION ALL
SELECT 'Bookings', COUNT(*) FROM Bookings
UNION ALL
SELECT 'ChargingSessions', COUNT(*) FROM ChargingSessions
UNION ALL
SELECT 'Payments', COUNT(*) FROM Payments
UNION ALL
SELECT 'AuditLogs', COUNT(*) FROM AuditLogs
UNION ALL
SELECT 'SystemSettings', COUNT(*) FROM SystemSettings;

-- ------------------------------------------------------------
-- TEST 3: FOREIGN KEY ORPHAN AUDIT (REFERENTIAL INTEGRITY)
-- Every count MUST BE ZERO for 100% integrity.
-- ------------------------------------------------------------
SELECT 
    'Orphaned Vehicles (Invalid user_id)' AS integrity_check,
    COUNT(*) AS orphan_count
FROM Vehicles v
LEFT JOIN Users u ON v.user_id = u.user_id
WHERE u.user_id IS NULL

UNION ALL

SELECT 
    'Orphaned ChargingPoints (Invalid station_id)',
    COUNT(*)
FROM ChargingPoints cp
LEFT JOIN Stations s ON cp.station_id = s.station_id
WHERE s.station_id IS NULL

UNION ALL

SELECT 
    'Orphaned Bookings (Invalid user, vehicle, or point)',
    COUNT(*)
FROM Bookings b
LEFT JOIN Users u ON b.user_id = u.user_id
LEFT JOIN Vehicles v ON b.vehicle_id = v.vehicle_id
LEFT JOIN ChargingPoints cp ON b.point_id = cp.point_id
WHERE u.user_id IS NULL OR v.vehicle_id IS NULL OR cp.point_id IS NULL

UNION ALL

SELECT 
    'Orphaned Sessions (Invalid booking, user, or point)',
    COUNT(*)
FROM ChargingSessions cs
LEFT JOIN Bookings b ON cs.booking_id = b.booking_id
LEFT JOIN Users u ON cs.user_id = u.user_id
LEFT JOIN ChargingPoints cp ON cs.point_id = cp.point_id
WHERE (cs.booking_id IS NOT NULL AND b.booking_id IS NULL) 
   OR u.user_id IS NULL 
   OR cp.point_id IS NULL

UNION ALL

SELECT 
    'Orphaned Payments (Invalid session_id)',
    COUNT(*)
FROM Payments p
LEFT JOIN ChargingSessions cs ON p.session_id = cs.session_id
WHERE cs.session_id IS NULL;

-- ------------------------------------------------------------
-- TEST 4: STORED FUNCTION TEST (CalculateChargingCost)
-- Expected Output: 729.00 (40.500 kWh * 18.00 ₹/kWh)
-- ------------------------------------------------------------
SELECT 
    40.500 AS test_energy_kwh,
    18.00 AS test_tariff,
    CalculateChargingCost(40.500, 18.00) AS computed_total_cost,
    CASE 
        WHEN CalculateChargingCost(40.500, 18.00) = 729.00 THEN 'PASSED'
        ELSE 'FAILED'
    END AS function_test_status;

-- ------------------------------------------------------------
-- TEST 5: PROCEDURES & TRIGGERS CATALOG
-- ------------------------------------------------------------
SELECT ROUTINE_TYPE, ROUTINE_NAME, DEFINER, IS_DETERMINISTIC
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'ev_charging_db';

SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE, ACTION_TIMING
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'ev_charging_db';

-- ------------------------------------------------------------
-- TEST 6: SIMULATE TRANSACTION ROLLBACK INTEGRITY
-- Verifies that a failed operation cleanly leaves no partial state
-- ------------------------------------------------------------
START TRANSACTION;

-- Insert a test vehicle
INSERT INTO Vehicles (user_id, registration_no, make, model, battery_capacity_kwh)
VALUES (2, 'TEST-ROLLBACK-01', 'TestMake', 'TestModel', 50.00);

-- Verify presence inside the transaction
SELECT 'Vehicle inserted in uncommitted transaction' AS step, COUNT(*) AS count
FROM Vehicles WHERE registration_no = 'TEST-ROLLBACK-01';

-- Intentionally roll back
ROLLBACK;

-- Verify absence after rollback
SELECT 
    'Post-Rollback Verification' AS step,
    COUNT(*) AS count,
    CASE WHEN COUNT(*) = 0 THEN 'ROLLBACK_VERIFIED' ELSE 'ROLLBACK_FAILED' END AS result
FROM Vehicles WHERE registration_no = 'TEST-ROLLBACK-01';
