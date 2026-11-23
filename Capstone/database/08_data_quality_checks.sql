-- ============================================================
-- DATABASE QUALITY & INTEGRITY AUDIT SUITE
-- EV Charging Station Management System - DBMS Capstone Project
-- File: database/08_data_quality_checks.sql
-- Target DBMS: MySQL 8.0+ (InnoDB Engine)
-- Database: ev_charging_db
-- Description: Diagnostic SQL checks to verify 3NF integrity,
--              detect orphaned records, temporal overlaps,
--              monetary mismatches, and status anomalies.
-- ============================================================

USE ev_charging_db;

SELECT '==================================================' AS status_banner;
SELECT 'STARTING COMPREHENSIVE DATA QUALITY AUDIT' AS audit_status;
SELECT NOW() AS audit_execution_time;
SELECT '==================================================' AS status_banner;


-- ============================================================
-- CHECK 1: ORPHANED FOREIGN KEY AUDIT
-- Expected Result: 0 rows for every sub-query
-- ============================================================
SELECT 'CHECK 1: Inspecting for orphaned foreign key references...' AS check_description;

-- 1A: Vehicles without a valid owner in Users
SELECT 
    'Orphaned Vehicles' AS anomaly_type,
    v.vehicle_id, v.user_id, v.make, v.model, v.registration_no
FROM Vehicles v
LEFT JOIN Users u ON v.user_id = u.user_id
WHERE u.user_id IS NULL;

-- 1B: Charging Points without a valid parent Station
SELECT 
    'Orphaned Charging Points' AS anomaly_type,
    cp.point_id, cp.station_id, cp.point_code
FROM ChargingPoints cp
LEFT JOIN Stations s ON cp.station_id = s.station_id
WHERE s.station_id IS NULL;

-- 1C: Bookings referencing non-existent User, Point, or Vehicle
SELECT 
    'Orphaned Bookings' AS anomaly_type,
    b.booking_id, b.user_id, b.point_id, b.vehicle_id
FROM Bookings b
LEFT JOIN Users u ON b.user_id = u.user_id
LEFT JOIN ChargingPoints cp ON b.point_id = cp.point_id
LEFT JOIN Vehicles v ON b.vehicle_id = v.vehicle_id
WHERE u.user_id IS NULL OR cp.point_id IS NULL OR v.vehicle_id IS NULL;

-- 1D: Charging Sessions referencing non-existent Booking, User, Vehicle, or Point
SELECT 
    'Orphaned Sessions' AS anomaly_type,
    cs.session_id, cs.booking_id, cs.point_id, cs.user_id, cs.vehicle_id
FROM ChargingSessions cs
LEFT JOIN Bookings b ON cs.booking_id = b.booking_id
LEFT JOIN ChargingPoints cp ON cs.point_id = cp.point_id
LEFT JOIN Users u ON cs.user_id = u.user_id
LEFT JOIN Vehicles v ON cs.vehicle_id = v.vehicle_id
WHERE (cs.booking_id IS NOT NULL AND b.booking_id IS NULL) 
   OR cp.point_id IS NULL 
   OR u.user_id IS NULL 
   OR v.vehicle_id IS NULL;

-- 1E: Payments referencing non-existent Session
SELECT 
    'Orphaned Payments' AS anomaly_type,
    p.payment_id, p.session_id, p.transaction_reference
FROM Payments p
LEFT JOIN ChargingSessions cs ON p.session_id = cs.session_id
WHERE cs.session_id IS NULL;


-- ============================================================
-- CHECK 2: VEHICLE OWNERSHIP INTEGRITY IN BOOKINGS
-- Rule: The customer booking a point MUST own the selected vehicle
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 2: Verifying customer owns selected vehicle in Bookings...' AS check_description;

SELECT 
    'Mismatched Vehicle Ownership' AS anomaly_type,
    b.booking_id,
    b.user_id AS booking_user_id,
    v.user_id AS vehicle_owner_id,
    v.registration_no,
    b.created_at
FROM Bookings b
JOIN Vehicles v ON b.vehicle_id = v.vehicle_id
WHERE b.user_id <> v.user_id;


-- ============================================================
-- CHECK 3: BOOKING TEMPORAL INTEGRITY
-- Rule: start_at must be strictly earlier than end_at
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 3: Verifying chronological booking intervals (start < end)...' AS check_description;

SELECT 
    'Invalid Time Interval' AS anomaly_type,
    booking_id,
    user_id,
    point_id,
    start_at,
    end_at,
    TIMESTAMPDIFF(MINUTE, start_at, end_at) AS duration_minutes
FROM Bookings
WHERE start_at >= end_at;


-- ============================================================
-- CHECK 4: CONCURRENT BOOKING OVERLAP CONFLICTS
-- Rule: Two active bookings for the same charging point cannot overlap:
--       (b1.start_at < b2.end_at AND b1.end_at > b2.start_at)
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 4: Detecting conflicting overlapping active reservations...' AS check_description;

SELECT 
    'Overlapping Bookings Detected' AS anomaly_type,
    b1.booking_id AS booking_1_id,
    b2.booking_id AS booking_2_id,
    b1.point_id,
    b1.start_at AS b1_start,
    b1.end_at AS b1_end,
    b2.start_at AS b2_start,
    b2.end_at AS b2_end,
    b1.booking_status AS b1_status,
    b2.booking_status AS b2_status
FROM Bookings b1
JOIN Bookings b2 ON b1.point_id = b2.point_id 
    AND b1.booking_id < b2.booking_id
WHERE b1.booking_status IN ('PENDING', 'CONFIRMED')
  AND b2.booking_status IN ('PENDING', 'CONFIRMED')
  AND (b1.start_at < b2.end_at AND b1.end_at > b2.start_at);


-- ============================================================
-- CHECK 5: CHARGING SESSION TO BOOKING DISPENSER MISMATCH
-- Rule: Session point_id must match the parent booking's point_id
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 5: Verifying session charging point matches booking point...' AS check_description;

SELECT 
    'Mismatched Dispenser ID' AS anomaly_type,
    cs.session_id,
    cs.booking_id,
    cs.point_id AS session_point_id,
    b.point_id AS booking_point_id
FROM ChargingSessions cs
JOIN Bookings b ON cs.booking_id = b.booking_id
WHERE cs.point_id <> b.point_id;


-- ============================================================
-- CHECK 6: CHARGING SESSION COST & TARIFF RECONCILIATION
-- Rule: Completed session total_cost must match energy_kwh * tariff_per_kwh
--       within 0.05 rounding tolerance.
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 6: Reconciling session total_cost against energy * tariff...' AS check_description;

SELECT 
    'Tariff Calculation Mismatch' AS anomaly_type,
    session_id,
    energy_kwh,
    tariff_per_kwh,
    total_cost AS recorded_cost,
    ROUND(energy_kwh * tariff_per_kwh, 2) AS expected_cost,
    ABS(total_cost - ROUND(energy_kwh * tariff_per_kwh, 2)) AS discrepancy
FROM ChargingSessions
WHERE session_status = 'COMPLETED'
  AND ABS(total_cost - ROUND(energy_kwh * tariff_per_kwh, 2)) > 0.05;


-- ============================================================
-- CHECK 7: PAYMENT TO SESSION SETTLEMENT RECONCILIATION
-- Rule: Successful payment amount must match the session's total_cost
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 7: Verifying payment amounts equal session total costs...' AS check_description;

SELECT 
    'Payment Amount Mismatch' AS anomaly_type,
    p.payment_id,
    p.session_id,
    p.amount AS payment_amount,
    cs.total_cost AS session_cost,
    ABS(p.amount - cs.total_cost) AS discrepancy
FROM Payments p
JOIN ChargingSessions cs ON p.session_id = cs.session_id
WHERE p.payment_status = 'SUCCESS'
  AND cs.session_status = 'COMPLETED'
  AND ABS(p.amount - cs.total_cost) > 0.01;


-- ============================================================
-- CHECK 8: UNPAID COMPLETED SESSIONS AUDIT
-- Rule: All completed sessions should either have a SUCCESS or PENDING payment
-- Expected Result: 0 rows (unless pending settlement)
-- ============================================================
SELECT 'CHECK 8: Auditing completed sessions without successful payment...' AS check_description;

SELECT 
    'Unsettled Completed Session' AS anomaly_type,
    cs.session_id,
    cs.booking_id,
    cs.total_cost,
    cs.end_at,
    COALESCE(p.payment_status, 'NO_PAYMENT_RECORD') AS current_payment_status
FROM ChargingSessions cs
LEFT JOIN Payments p ON cs.session_id = p.session_id
WHERE cs.session_status = 'COMPLETED'
  AND (p.payment_status IS NULL OR p.payment_status NOT IN ('SUCCESS', 'PENDING'));


-- ============================================================
-- CHECK 9: DUPLICATE COMPLETED SESSIONS PER BOOKING
-- Rule: A booking can have at most ONE charging session
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 9: Checking for duplicate charging sessions per booking...' AS check_description;

SELECT 
    'Duplicate Session per Booking' AS anomaly_type,
    booking_id,
    COUNT(session_id) AS total_sessions
FROM ChargingSessions
WHERE booking_id IS NOT NULL
GROUP BY booking_id
HAVING COUNT(session_id) > 1;


-- ============================================================
-- CHECK 10: MONETARY & ENERGY NEGATIVE VALUE DETECTOR
-- Rule: Tariff, Power, Cost, and Energy values must all be >= 0.00
-- Expected Result: 0 rows
-- ============================================================
SELECT 'CHECK 10: Checking for negative power, energy, or monetary figures...' AS check_description;

SELECT 'Negative Power/Tariff in ChargingPoints' AS anomaly_type, point_id, point_code, max_power_kw, tariff_per_kwh
FROM ChargingPoints WHERE max_power_kw < 0 OR tariff_per_kwh < 0
UNION ALL
SELECT 'Negative Energy/Cost in ChargingSessions' AS anomaly_type, session_id, booking_id, energy_kwh, total_cost
FROM ChargingSessions WHERE energy_kwh < 0 OR total_cost < 0
UNION ALL
SELECT 'Negative Amount in Payments' AS anomaly_type, payment_id, session_id, amount, 0
FROM Payments WHERE amount < 0;


-- ============================================================
-- FINAL SUMMARY SCORECARD
-- Aggregates all integrity checks into an executive pass/fail matrix
-- ============================================================
SELECT '==================================================' AS summary_banner;
SELECT 'DATA INTEGRITY AUDIT SCORECARD' AS scorecard_title;
SELECT '==================================================' AS summary_banner;

SELECT 
    'Check 1: Orphan Foreign Keys' AS audit_metric,
    (SELECT COUNT(*) FROM Vehicles v LEFT JOIN Users u ON v.user_id = u.user_id WHERE u.user_id IS NULL) +
    (SELECT COUNT(*) FROM ChargingPoints cp LEFT JOIN Stations s ON cp.station_id = s.station_id WHERE s.station_id IS NULL) +
    (SELECT COUNT(*) FROM Bookings b LEFT JOIN Users u ON b.user_id = u.user_id WHERE u.user_id IS NULL) +
    (SELECT COUNT(*) FROM ChargingSessions cs LEFT JOIN Bookings b ON cs.booking_id = b.booking_id WHERE cs.booking_id IS NOT NULL AND b.booking_id IS NULL) +
    (SELECT COUNT(*) FROM Payments p LEFT JOIN ChargingSessions cs ON p.session_id = cs.session_id WHERE cs.session_id IS NULL) AS violations_found,
    CASE 
        WHEN ((SELECT COUNT(*) FROM Vehicles v LEFT JOIN Users u ON v.user_id = u.user_id WHERE u.user_id IS NULL) +
              (SELECT COUNT(*) FROM ChargingPoints cp LEFT JOIN Stations s ON cp.station_id = s.station_id WHERE s.station_id IS NULL) +
              (SELECT COUNT(*) FROM Bookings b LEFT JOIN Users u ON b.user_id = u.user_id WHERE u.user_id IS NULL) +
              (SELECT COUNT(*) FROM ChargingSessions cs LEFT JOIN Bookings b ON cs.booking_id = b.booking_id WHERE cs.booking_id IS NOT NULL AND b.booking_id IS NULL) +
              (SELECT COUNT(*) FROM Payments p LEFT JOIN ChargingSessions cs ON p.session_id = cs.session_id WHERE cs.session_id IS NULL)) = 0 
        THEN '100% PASS' ELSE 'FAIL' 
    END AS audit_status

UNION ALL

SELECT 
    'Check 2: Vehicle Ownership' AS audit_metric,
    COUNT(*) AS violations_found,
    CASE WHEN COUNT(*) = 0 THEN '100% PASS' ELSE 'FAIL' END AS audit_status
FROM Bookings b JOIN Vehicles v ON b.vehicle_id = v.vehicle_id WHERE b.user_id <> v.user_id

UNION ALL

SELECT 
    'Check 3: Chronological Booking Intervals' AS audit_metric,
    COUNT(*) AS violations_found,
    CASE WHEN COUNT(*) = 0 THEN '100% PASS' ELSE 'FAIL' END AS audit_status
FROM Bookings WHERE start_at >= end_at

UNION ALL

SELECT 
    'Check 4: Overlapping Active Bookings' AS audit_metric,
    COUNT(*) AS violations_found,
    CASE WHEN COUNT(*) = 0 THEN '100% PASS' ELSE 'FAIL' END AS audit_status
FROM Bookings b1
JOIN Bookings b2 ON b1.point_id = b2.point_id AND b1.booking_id < b2.booking_id
WHERE b1.booking_status IN ('PENDING', 'CONFIRMED')
  AND b2.booking_status IN ('PENDING', 'CONFIRMED')
  AND (b1.start_at < b2.end_at AND b1.end_at > b2.start_at)

UNION ALL

SELECT 
    'Check 5: Session Dispenser Alignment' AS audit_metric,
    COUNT(*) AS violations_found,
    CASE WHEN COUNT(*) = 0 THEN '100% PASS' ELSE 'FAIL' END AS audit_status
FROM ChargingSessions cs JOIN Bookings b ON cs.booking_id = b.booking_id WHERE cs.point_id <> b.point_id

UNION ALL

SELECT 
    'Check 6: Energy * Tariff Cost Match' AS audit_metric,
    COUNT(*) AS violations_found,
    CASE WHEN COUNT(*) = 0 THEN '100% PASS' ELSE 'FAIL' END AS audit_status
FROM ChargingSessions
WHERE session_status = 'COMPLETED'
  AND ABS(total_cost - ROUND(energy_kwh * tariff_per_kwh, 2)) > 0.05

UNION ALL

SELECT 
    'Check 7: Payment-to-Session Match' AS audit_metric,
    COUNT(*) AS violations_found,
    CASE WHEN COUNT(*) = 0 THEN '100% PASS' ELSE 'FAIL' END AS audit_status
FROM Payments p JOIN ChargingSessions cs ON p.session_id = cs.session_id
WHERE p.payment_status = 'SUCCESS' AND cs.session_status = 'COMPLETED' AND ABS(p.amount - cs.total_cost) > 0.01

UNION ALL

SELECT 
    'Check 8: Non-Negative Figures' AS audit_metric,
    (SELECT COUNT(*) FROM ChargingPoints WHERE max_power_kw < 0 OR tariff_per_kwh < 0) +
    (SELECT COUNT(*) FROM ChargingSessions WHERE energy_kwh < 0 OR total_cost < 0) +
    (SELECT COUNT(*) FROM Payments WHERE amount < 0) AS violations_found,
    CASE 
        WHEN ((SELECT COUNT(*) FROM ChargingPoints WHERE max_power_kw < 0 OR tariff_per_kwh < 0) +
              (SELECT COUNT(*) FROM ChargingSessions WHERE energy_kwh < 0 OR total_cost < 0) +
              (SELECT COUNT(*) FROM Payments WHERE amount < 0)) = 0 
        THEN '100% PASS' ELSE 'FAIL' 
    END AS audit_status;
