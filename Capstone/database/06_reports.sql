-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 6: ANALYTICS & REPORTS
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/06_reports.sql
-- Description: Production-grade analytical queries for executive dashboards,
--              financial reconciliation, station utilization, and EXPLAIN plans.
-- ============================================================

USE ev_charging_db;

-- ------------------------------------------------------------
-- REPORT 1: STATION & CHARGING POINT OPERATIONAL AVAILABILITY
-- Aggregates total dispensers and live status counts per station
-- ------------------------------------------------------------
SELECT 
    s.station_id,
    s.station_name,
    s.city,
    s.station_status,
    COUNT(cp.point_id) AS total_points,
    SUM(CASE WHEN cp.point_status = 'AVAILABLE' THEN 1 ELSE 0 END) AS available_points,
    SUM(CASE WHEN cp.point_status = 'OCCUPIED' THEN 1 ELSE 0 END) AS occupied_points,
    SUM(CASE WHEN cp.point_status = 'MAINTENANCE' THEN 1 ELSE 0 END) AS maintenance_points,
    ROUND(
        (SUM(CASE WHEN cp.point_status = 'AVAILABLE' THEN 1 ELSE 0 END) / COUNT(cp.point_id)) * 100, 
        1
    ) AS availability_pct
FROM Stations s
LEFT JOIN ChargingPoints cp ON s.station_id = cp.station_id
GROUP BY s.station_id, s.station_name, s.city, s.station_status
ORDER BY availability_pct DESC;

-- ------------------------------------------------------------
-- REPORT 2: MONTHLY REVENUE BY STATION & CITY
-- Aggregates financial performance across calendar months
-- ------------------------------------------------------------
SELECT 
    DATE_FORMAT(p.paid_at, '%Y-%m') AS billing_month,
    s.station_name,
    s.city,
    COUNT(p.payment_id) AS settled_transactions,
    ROUND(SUM(p.amount), 2) AS total_revenue_inr,
    ROUND(AVG(p.amount), 2) AS average_ticket_size_inr
FROM Payments p
JOIN ChargingSessions cs ON p.session_id = cs.session_id
JOIN ChargingPoints cp ON cs.point_id = cp.point_id
JOIN Stations s ON cp.station_id = s.station_id
WHERE p.payment_status = 'SUCCESS'
GROUP BY DATE_FORMAT(p.paid_at, '%Y-%m'), s.station_name, s.city
ORDER BY billing_month DESC, total_revenue_inr DESC;

-- ------------------------------------------------------------
-- REPORT 3: MONTHLY ENERGY CONSUMPTION TRENDS
-- Measures clean energy dispensed (kWh) by station
-- ------------------------------------------------------------
SELECT 
    DATE_FORMAT(cs.start_at, '%Y-%m') AS usage_month,
    s.station_name,
    COUNT(cs.session_id) AS total_sessions,
    ROUND(SUM(cs.energy_kwh), 2) AS total_energy_kwh,
    ROUND(AVG(cs.energy_kwh), 2) AS avg_energy_per_session_kwh,
    ROUND(SUM(cs.total_cost), 2) AS total_session_charges
FROM ChargingSessions cs
JOIN ChargingPoints cp ON cs.point_id = cp.point_id
JOIN Stations s ON cp.station_id = s.station_id
WHERE cs.session_status = 'COMPLETED'
GROUP BY DATE_FORMAT(cs.start_at, '%Y-%m'), s.station_name
ORDER BY usage_month DESC, total_energy_kwh DESC;

-- ------------------------------------------------------------
-- REPORT 4: BOOKING STATUS DISTRIBUTION
-- High-level operational health of slot reservations
-- ------------------------------------------------------------
SELECT 
    booking_status,
    COUNT(*) AS total_bookings,
    ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM Bookings)), 1) AS percentage_of_total
FROM Bookings
GROUP BY booking_status
ORDER BY total_bookings DESC;

-- ------------------------------------------------------------
-- REPORT 5: TOP CUSTOMERS BY CONSUMPTION & SPENDING
-- Identifies highest-volume EV owners across the charging network
-- ------------------------------------------------------------
SELECT 
    u.user_id,
    u.full_name AS customer_name,
    u.email,
    COUNT(DISTINCT v.vehicle_id) AS registered_vehicles,
    COUNT(cs.session_id) AS total_completed_sessions,
    ROUND(COALESCE(SUM(cs.energy_kwh), 0), 2) AS total_kwh_consumed,
    ROUND(COALESCE(SUM(p.amount), 0), 2) AS total_spent_inr
FROM Users u
LEFT JOIN Vehicles v ON u.user_id = v.user_id
LEFT JOIN ChargingSessions cs ON u.user_id = cs.user_id AND cs.session_status = 'COMPLETED'
LEFT JOIN Payments p ON cs.session_id = p.session_id AND p.payment_status = 'SUCCESS'
WHERE u.role = 'OWNER'
GROUP BY u.user_id, u.full_name, u.email
ORDER BY total_spent_inr DESC
LIMIT 10;

-- ------------------------------------------------------------
-- REPORT 6: FINANCIAL RECONCILIATION & DATA QUALITY AUDIT
-- Checks whether any payment amount deviates from session total_cost
-- Expected output: 0 discrepancy rows
-- ------------------------------------------------------------
SELECT 
    p.payment_id,
    p.transaction_reference,
    p.amount AS payment_amount,
    cs.total_cost AS session_cost,
    ROUND(p.amount - cs.total_cost, 2) AS discrepancy,
    p.payment_status,
    cs.session_status
FROM Payments p
JOIN ChargingSessions cs ON p.session_id = cs.session_id
WHERE ABS(p.amount - cs.total_cost) > 0.01;

-- ------------------------------------------------------------
-- REPORT 7: QUERY PLAN PERFORMANCE WITH EXPLAIN
-- Analyzes execution plan for booking overlap lookup
-- ------------------------------------------------------------
EXPLAIN
SELECT booking_id
FROM Bookings
WHERE point_id = 1
  AND booking_status IN ('PENDING', 'CONFIRMED')
  AND '2026-10-25 10:00:00' < end_at
  AND '2026-10-25 11:00:00' > start_at;

EXPLAIN FORMAT=TREE
SELECT 
    s.station_name, 
    SUM(p.amount) AS revenue
FROM Payments p
JOIN ChargingSessions cs ON p.session_id = cs.session_id
JOIN ChargingPoints cp ON cs.point_id = cp.point_id
JOIN Stations s ON cp.station_id = s.station_id
WHERE p.payment_status = 'SUCCESS'
GROUP BY s.station_name;
