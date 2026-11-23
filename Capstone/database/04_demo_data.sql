-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 4: SYNTHETIC DEMONSTRATION DATA
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/04_demo_data.sql
-- Description: Realistic synthetic seed records spanning users, vehicles,
--              stations, charging points, bookings, sessions, payments,
--              audit logs, and system settings.
-- ============================================================

USE ev_charging_db;

-- ------------------------------------------------------------
-- 1. USERS TABLE (1 Admin + 10 EV Owners)
-- Passwords:
--   admin@evdemo.com  -> Admin@123
--   All other users   -> Owner@123
-- ------------------------------------------------------------
INSERT INTO Users (user_id, full_name, email, phone, password_hash, role, account_status)
VALUES
(1, 'System Admin', 'admin@evdemo.com', '9000000001', 'scrypt:32768:8:1$XYd8REFIemS8eE1j$e6dc318f9eaf7ca8b113cea9c77cc748653347dd6642d9acc72f9cb4f4578f3066abfc9874cd5500f98ae9d7623a9cbf42a5cd5c87f0bda766f3b984d05a5c7c', 'ADMIN', 'ACTIVE'),
(2, 'Aarav Sharma', 'aarav@example.com', '9000000002', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(3, 'Priya Verma', 'priya@example.com', '9000000003', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(4, 'Rohan Gupta', 'rohan@example.com', '9000000004', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(5, 'Ananya Singh', 'ananya@example.com', '9000000005', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(6, 'Kabir Mehta', 'kabir@example.com', '9000000006', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(7, 'Ishita Rao', 'ishita@example.com', '9000000007', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(8, 'Arjun Nair', 'arjun@example.com', '9000000008', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(9, 'Meera Joshi', 'meera@example.com', '9000000009', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(10, 'Dev Malhotra', 'dev@example.com', '9000000010', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE'),
(11, 'Sara Khan', 'sara@example.com', '9000000011', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE')
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name), password_hash = VALUES(password_hash);

-- ------------------------------------------------------------
-- 2. VEHICLES TABLE (10 Electric Vehicles)
-- ------------------------------------------------------------
INSERT INTO Vehicles (vehicle_id, user_id, registration_no, make, model, battery_capacity_kwh)
VALUES
(1, 2, 'DL01EV1001', 'Tata', 'Nexon EV', 40.50),
(2, 3, 'DL01EV1002', 'MG', 'ZS EV', 50.30),
(3, 4, 'DL01EV1003', 'Hyundai', 'Kona Electric', 39.20),
(4, 5, 'DL01EV1004', 'Tata', 'Tiago EV', 24.00),
(5, 6, 'DL01EV1005', 'Mahindra', 'XUV400', 39.40),
(6, 7, 'DL01EV1006', 'BYD', 'Atto 3', 60.50),
(7, 8, 'DL01EV1007', 'Tata', 'Nexon EV Max', 40.50),
(8, 9, 'DL01EV1008', 'MG', 'Comet EV', 17.30),
(9, 10, 'DL01EV1009', 'Citroen', 'eC3', 29.20),
(10, 11, 'DL01EV1010', 'Hyundai', 'Ioniq 5', 72.60)
ON DUPLICATE KEY UPDATE make = VALUES(make), model = VALUES(model);

-- ------------------------------------------------------------
-- 3. CHARGING STATIONS TABLE (3 Physical Hubs)
-- ------------------------------------------------------------
INSERT INTO Stations (station_id, station_name, address, city, opening_time, closing_time, station_status)
VALUES
(1, 'Connaught Place EV Hub', 'Inner Circle, Block C, Connaught Place', 'New Delhi', '06:00:00', '23:00:00', 'ACTIVE'),
(2, 'Gurugram Central Charge', 'Sector 29, Leisure Valley Road', 'Gurugram', '00:00:00', '23:59:59', 'ACTIVE'),
(3, 'Noida Green Charge', 'Sector 18 Market Complex', 'Noida', '06:00:00', '23:00:00', 'ACTIVE')
ON DUPLICATE KEY UPDATE station_name = VALUES(station_name), city = VALUES(city);

-- ------------------------------------------------------------
-- 4. CHARGING POINTS TABLE (6 Dispensers)
-- ------------------------------------------------------------
INSERT INTO ChargingPoints (point_id, station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
VALUES
(1, 1, 'CP-01', 'CCS2', 60.00, 18.00, 'AVAILABLE'),
(2, 1, 'CP-02', 'TYPE2', 22.00, 12.00, 'AVAILABLE'),
(3, 2, 'CP-01', 'CCS2', 120.00, 20.00, 'AVAILABLE'),
(4, 2, 'CP-02', 'CHADEMO', 50.00, 17.00, 'AVAILABLE'),
(5, 3, 'CP-01', 'CCS2', 60.00, 18.50, 'AVAILABLE'),
(6, 3, 'CP-02', 'TYPE2', 22.00, 11.50, 'AVAILABLE')
ON DUPLICATE KEY UPDATE max_power_kw = VALUES(max_power_kw), tariff_per_kwh = VALUES(tariff_per_kwh);

-- ------------------------------------------------------------
-- 5. BOOKINGS TABLE (Historical and Active Reservations)
-- ------------------------------------------------------------
INSERT INTO Bookings (booking_id, user_id, vehicle_id, point_id, start_at, end_at, booking_status)
VALUES
(1, 2, 1, 1, '2026-08-05 09:00:00', '2026-08-05 10:00:00', 'COMPLETED'),
(2, 3, 2, 2, '2026-08-10 11:00:00', '2026-08-10 12:00:00', 'COMPLETED'),
(3, 4, 3, 3, '2026-09-02 13:00:00', '2026-09-02 14:00:00', 'COMPLETED'),
(4, 5, 4, 4, '2026-09-12 15:00:00', '2026-09-12 16:00:00', 'COMPLETED'),
(5, 6, 5, 5, '2026-10-02 10:00:00', '2026-10-02 11:00:00', 'COMPLETED'),
(6, 7, 6, 6, '2026-10-08 14:00:00', '2026-10-08 15:00:00', 'COMPLETED'),
(7, 8, 7, 1, '2026-10-25 09:00:00', '2026-10-25 10:00:00', 'CONFIRMED'),
(8, 9, 8, 2, '2026-10-26 12:00:00', '2026-10-26 13:00:00', 'CONFIRMED')
ON DUPLICATE KEY UPDATE booking_status = VALUES(booking_status);

-- ------------------------------------------------------------
-- 6. CHARGING SESSIONS TABLE (Completed and Metered Sessions)
-- ------------------------------------------------------------
INSERT INTO ChargingSessions (session_id, booking_id, user_id, vehicle_id, point_id, start_at, end_at, energy_kwh, tariff_per_kwh, total_cost, session_status)
VALUES
(1, 1, 2, 1, 1, '2026-08-05 09:00:00', '2026-08-05 09:45:00', 30.000, 18.00, 540.00, 'COMPLETED'),
(2, 2, 3, 2, 2, '2026-08-10 11:00:00', '2026-08-10 11:50:00', 15.000, 12.00, 180.00, 'COMPLETED'),
(3, 3, 4, 3, 3, '2026-09-02 13:00:00', '2026-09-02 13:40:00', 35.000, 20.00, 700.00, 'COMPLETED'),
(4, 4, 5, 4, 4, '2026-09-12 15:00:00', '2026-09-12 15:45:00', 20.000, 17.00, 340.00, 'COMPLETED'),
(5, 5, 6, 5, 5, '2026-10-02 10:00:00', '2026-10-02 10:40:00', 28.000, 18.50, 518.00, 'COMPLETED'),
(6, 6, 7, 6, 6, '2026-10-08 14:00:00', '2026-10-08 14:30:00', 12.000, 11.50, 138.00, 'COMPLETED')
ON DUPLICATE KEY UPDATE energy_kwh = VALUES(energy_kwh), total_cost = VALUES(total_cost);

-- ------------------------------------------------------------
-- 7. PAYMENTS TABLE (Settled Financial Records)
-- ------------------------------------------------------------
INSERT INTO Payments (payment_id, session_id, transaction_reference, amount, payment_method, payment_status, paid_at)
VALUES
(1, 1, 'EVTXN-0001', 540.00, 'UPI', 'SUCCESS', '2026-08-05 09:50:00'),
(2, 2, 'EVTXN-0002', 180.00, 'CARD', 'SUCCESS', '2026-08-10 11:55:00'),
(3, 3, 'EVTXN-0003', 700.00, 'UPI', 'SUCCESS', '2026-09-02 13:45:00'),
(4, 4, 'EVTXN-0004', 340.00, 'WALLET', 'SUCCESS', '2026-09-12 15:50:00'),
(5, 5, 'EVTXN-0005', 518.00, 'UPI', 'SUCCESS', '2026-10-02 10:45:00'),
(6, 6, 'EVTXN-0006', 138.00, 'CARD', 'SUCCESS', '2026-10-08 14:35:00')
ON DUPLICATE KEY UPDATE payment_status = VALUES(payment_status);

-- ------------------------------------------------------------
-- 8. AUDIT LOGS (Demonstrating Administrative Traceability)
-- ------------------------------------------------------------
INSERT INTO AuditLogs (log_id, user_id, action, entity_name, entity_id, details, ip_address, created_at)
VALUES
(1, 1, 'CREATE_STATION', 'Stations', 1, 'Provisioned initial station: Connaught Place EV Hub in New Delhi', '127.0.0.1', '2026-08-01 08:00:00'),
(2, 1, 'CREATE_POINT', 'ChargingPoints', 1, 'Configured dispenser CP-01 (60kW CCS2) at Connaught Place', '127.0.0.1', '2026-08-01 08:30:00'),
(3, 1, 'UPDATE_SETTING', 'SystemSettings', NULL, 'Configured GST tax rate to 18.00%', '127.0.0.1', '2026-08-01 09:00:00')
ON DUPLICATE KEY UPDATE action = VALUES(action);

-- ------------------------------------------------------------
-- 9. SYSTEM SETTINGS (Application Thresholds)
-- ------------------------------------------------------------
INSERT INTO SystemSettings (setting_key, setting_value, description)
VALUES
('tax_rate_percent', '18.00', 'Goods and Services Tax (GST) rate applied to energy charging tariffs'),
('max_booking_hours', '6', 'Maximum permitted duration in hours for a single booking reservation'),
('cancellation_grace_mins', '15', 'Permitted cancellation lead time before scheduled start time in minutes'),
('min_battery_capacity_kwh', '5.0', 'Minimum supported EV battery capacity in kilowatt-hours'),
('app_currency', 'INR', 'Operational currency code for tariff display and billing calculations')
ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);

SELECT 'Synthetic demonstration data successfully seeded.' AS seed_status;
