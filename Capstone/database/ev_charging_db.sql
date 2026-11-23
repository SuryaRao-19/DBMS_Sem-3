-- =====================================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- MASTER DATABASE INITIALIZATION SCRIPT FOR MYSQL WORKBENCH
-- Target RDBMS: MySQL Server 8.0+ (InnoDB Storage Engine)
-- Script File: database/ev_charging_db.sql
-- =====================================================================
-- Instructions for MySQL Workbench:
-- 1. Open MySQL Workbench and connect to your local MySQL 8.0 server instance.
-- 2. Go to File -> Open SQL Script... and select this file: database/ev_charging_db.sql
-- 3. Click the Execute (Lightning Bolt) icon to execute the entire script.
-- 4. In the Navigator pane, right-click the Schemas list and click "Refresh All".
--    The schema 'ev_charging_db' will appear with all 7 tables, routines, and triggers.
-- =====================================================================

DROP DATABASE IF EXISTS ev_charging_db;
CREATE DATABASE ev_charging_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ev_charging_db;

-- =====================================================================
-- SECTION 1: RELATIONAL SCHEMA DEFINITION (3NF NORMALIZED)
-- =====================================================================

-- 1. USERS TABLE
-- Handles customer accounts, administrators, password security, and account status
CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('ADMIN', 'OWNER') NOT NULL DEFAULT 'OWNER',
    account_status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. VEHICLES TABLE
-- Stores EV details owned by registered users (EV Owners)
CREATE TABLE Vehicles (
    vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    registration_no VARCHAR(30) NOT NULL UNIQUE,
    make VARCHAR(60) NOT NULL,
    model VARCHAR(60) NOT NULL,
    battery_capacity_kwh DECIMAL(8,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CHECK (battery_capacity_kwh > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. STATIONS TABLE
-- Physical charging station hubs and operating hours
CREATE TABLE Stations (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    station_name VARCHAR(120) NOT NULL,
    address VARCHAR(255) NOT NULL,
    city VARCHAR(80) NOT NULL,
    opening_time TIME DEFAULT '06:00:00',
    closing_time TIME DEFAULT '23:00:00',
    station_status ENUM('ACTIVE', 'INACTIVE', 'MAINTENANCE') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. CHARGING POINTS TABLE
-- Individual charging dispensers with connector types, max power ratings, and tariffs
CREATE TABLE ChargingPoints (
    point_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    point_code VARCHAR(30) NOT NULL,
    connector_type ENUM('TYPE2', 'CCS2', 'CHADEMO', 'GB_T') NOT NULL,
    max_power_kw DECIMAL(8,2) NOT NULL,
    tariff_per_kwh DECIMAL(10,2) NOT NULL,
    point_status ENUM('AVAILABLE', 'OCCUPIED', 'UNAVAILABLE', 'MAINTENANCE') NOT NULL DEFAULT 'AVAILABLE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (station_id, point_code),
    FOREIGN KEY (station_id) REFERENCES Stations(station_id) ON DELETE CASCADE,
    CHECK (max_power_kw > 0),
    CHECK (tariff_per_kwh >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. BOOKINGS TABLE
-- Advance time slot reservations created by EV drivers
CREATE TABLE Bookings (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    point_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    booking_status ENUM('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED') NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id),
    FOREIGN KEY (vehicle_id) REFERENCES Vehicles(vehicle_id),
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id),
    CHECK (end_at > start_at),
    INDEX idx_booking_point_time (point_id, start_at, end_at),
    INDEX idx_booking_user_status (user_id, booking_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. CHARGING SESSIONS TABLE
-- Real-time energy dispensing events, durations, tariffs, and billings
CREATE TABLE ChargingSessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT UNIQUE,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    point_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME,
    energy_kwh DECIMAL(10,3) NOT NULL DEFAULT 0,
    tariff_per_kwh DECIMAL(10,2) NOT NULL,
    total_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
    session_status ENUM('IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'IN_PROGRESS',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES Bookings(booking_id),
    FOREIGN KEY (user_id) REFERENCES Users(user_id),
    FOREIGN KEY (vehicle_id) REFERENCES Vehicles(vehicle_id),
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id),
    CHECK (energy_kwh >= 0),
    CHECK (tariff_per_kwh >= 0),
    CHECK (total_cost >= 0),
    CHECK (end_at IS NULL OR end_at >= start_at),
    INDEX idx_session_user_date (user_id, start_at),
    INDEX idx_session_point_date (point_id, start_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. PAYMENTS TABLE
-- Ledger audit entries recording simulated financial settlements
CREATE TABLE Payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    transaction_reference VARCHAR(100) NOT NULL UNIQUE,
    amount DECIMAL(12,2) NOT NULL,
    payment_method ENUM('UPI', 'CARD', 'CASH', 'WALLET') NOT NULL,
    payment_status ENUM('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED') NOT NULL DEFAULT 'PENDING',
    paid_at DATETIME,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES ChargingSessions(session_id),
    CHECK (amount >= 0),
    INDEX idx_payment_status_date (payment_status, paid_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 8. AUDIT LOGS TABLE
-- Immutable audit trail of administrative modifications
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS AuditLogs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(80) NOT NULL,
    entity_name VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    details TEXT,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_audit_entity (entity_name, entity_id),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 9. SYSTEM SETTINGS TABLE
-- Database-backed dynamic operational parameters
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS SystemSettings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    description VARCHAR(255) NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
-- SECTION 2: PROCEDURAL SQL (FUNCTIONS, TRIGGERS, PROCEDURES)
-- =====================================================================

-- 1. STORED FUNCTION: CalculateChargingCost
DELIMITER $$
CREATE FUNCTION CalculateChargingCost(
    p_energy_kwh DECIMAL(10,3),
    p_tariff DECIMAL(10,2)
)
RETURNS DECIMAL(12,2)
DETERMINISTIC
NO SQL
BEGIN
    RETURN ROUND(p_energy_kwh * p_tariff, 2);
END$$
DELIMITER ;

-- 2. TRIGGER: trg_booking_before_insert
-- Enforces slot overlap collision prevention, vehicle ownership, and dispenser operational status
DELIMITER $$
CREATE TRIGGER trg_booking_before_insert
BEFORE INSERT ON Bookings
FOR EACH ROW
BEGIN
    DECLARE conflict_count INT DEFAULT 0;
    DECLARE owner_count INT DEFAULT 0;
    DECLARE point_count INT DEFAULT 0;

    -- Validate end time follows start time
    IF NEW.end_at <= NEW.start_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Booking end must be after start';
    END IF;

    -- Validate vehicle belongs to the booking user
    SELECT COUNT(*) INTO owner_count
    FROM Vehicles
    WHERE vehicle_id = NEW.vehicle_id
      AND user_id = NEW.user_id;

    IF owner_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Vehicle does not belong to this user';
    END IF;

    -- Validate charging point and station availability
    SELECT COUNT(*) INTO point_count
    FROM ChargingPoints cp
    JOIN Stations s ON s.station_id = cp.station_id
    WHERE cp.point_id = NEW.point_id
      AND cp.point_status = 'AVAILABLE'
      AND s.station_status = 'ACTIVE';

    IF point_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Charging point or station is unavailable';
    END IF;

    -- Reject overlapping bookings for the same point
    SELECT COUNT(*) INTO conflict_count
    FROM Bookings
    WHERE point_id = NEW.point_id
      AND booking_status IN ('PENDING', 'CONFIRMED')
      AND (NEW.booking_id IS NULL OR booking_id <> NEW.booking_id)
      AND NEW.start_at < end_at
      AND NEW.end_at > start_at;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Overlapping booking already exists';
    END IF;
END$$
DELIMITER ;

-- 3. STORED PROCEDURE: CompleteChargingSession
-- Completes session with row locking (FOR UPDATE), calculates cost, sets end timestamp, restores dispenser state
DELIMITER $$
CREATE PROCEDURE CompleteChargingSession(
    IN p_session_id INT,
    IN p_energy_kwh DECIMAL(10,3)
)
BEGIN
    DECLARE v_tariff DECIMAL(10,2);
    DECLARE v_status VARCHAR(20);
    DECLARE v_point_id INT;
    DECLARE v_start DATETIME;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_energy_kwh < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Energy consumed cannot be negative';
    END IF;

    START TRANSACTION;

    SELECT tariff_per_kwh, session_status, point_id, start_at
    INTO v_tariff, v_status, v_point_id, v_start
    FROM ChargingSessions
    WHERE session_id = p_session_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Session not found';
    END IF;

    IF v_status <> 'IN_PROGRESS' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Session is not in progress';
    END IF;

    UPDATE ChargingSessions
    SET energy_kwh = p_energy_kwh,
        end_at = CURRENT_TIMESTAMP,
        total_cost = CalculateChargingCost(p_energy_kwh, v_tariff),
        session_status = 'COMPLETED'
    WHERE session_id = p_session_id;

    UPDATE ChargingPoints
    SET point_status = 'AVAILABLE'
    WHERE point_id = v_point_id;

    COMMIT;
END$$
DELIMITER ;

-- 4. TRIGGER: trg_session_before_insert
DELIMITER $$
CREATE TRIGGER trg_session_before_insert
BEFORE INSERT ON ChargingSessions
FOR EACH ROW
BEGIN
    DECLARE v_owner_count INT DEFAULT 0;
    DECLARE v_point_count INT DEFAULT 0;

    IF NEW.energy_kwh < 0 OR NEW.tariff_per_kwh < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Energy and tariff must be non-negative';
    END IF;

    IF NEW.end_at IS NOT NULL AND NEW.end_at < NEW.start_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Session end cannot precede start';
    END IF;

    SELECT COUNT(*) INTO v_owner_count
    FROM Vehicles
    WHERE vehicle_id = NEW.vehicle_id
      AND user_id = NEW.user_id;

    IF v_owner_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Vehicle does not belong to session user';
    END IF;

    SELECT COUNT(*) INTO v_point_count
    FROM ChargingPoints
    WHERE point_id = NEW.point_id
      AND point_status = 'AVAILABLE';

    IF v_point_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Charging point is not available';
    END IF;
END$$
DELIMITER ;


-- =====================================================================
-- SECTION 3: SECONDARY COMPOSITE B-TREE INDEXES
-- =====================================================================

CREATE INDEX idx_stations_city_status ON Stations (city, station_status);
CREATE INDEX idx_cp_station_status ON ChargingPoints (station_id, point_status);


-- =====================================================================
-- SECTION 4: REALISTIC SYNTHETIC DEMONSTRATION DATA (3 MONTHS)
-- Default Demo Credentials:
--   System Admin: admin@evdemo.com  / Admin@123
--   EV Owner:     aarav@example.com / Owner@123
-- =====================================================================

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
(11, 'Sara Khan', 'sara@example.com', '9000000011', 'scrypt:32768:8:1$Kgw9S7ZsKtLiIAwy$30bf6bbe25ad4bf06b2306a7b888e88aa687941c6d747cdfafa1d449ff3e7af79568a619248f8f985a8d8116c57fcd205c51bafe0db0a1844aaec590c8ccbdc4', 'OWNER', 'ACTIVE');

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
(10, 11, 'DL01EV1010', 'Hyundai', 'Ioniq 5', 72.60);

INSERT INTO Stations (station_id, station_name, address, city, opening_time, closing_time, station_status)
VALUES
(1, 'Connaught Place EV Hub', 'Inner Circle, Block C, Connaught Place', 'New Delhi', '06:00:00', '23:00:00', 'ACTIVE'),
(2, 'Gurugram Central Charge', 'Sector 29, Leisure Valley Road', 'Gurugram', '00:00:00', '23:59:59', 'ACTIVE'),
(3, 'Noida Green Charge', 'Sector 18 Market Complex', 'Noida', '06:00:00', '23:00:00', 'ACTIVE');

INSERT INTO ChargingPoints (point_id, station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
VALUES
(1, 1, 'CP-01', 'CCS2', 60.00, 18.00, 'AVAILABLE'),
(2, 1, 'CP-02', 'TYPE2', 22.00, 12.00, 'AVAILABLE'),
(3, 2, 'CP-01', 'CCS2', 120.00, 20.00, 'AVAILABLE'),
(4, 2, 'CP-02', 'CHADEMO', 50.00, 17.00, 'AVAILABLE'),
(5, 3, 'CP-01', 'CCS2', 60.00, 18.50, 'AVAILABLE'),
(6, 3, 'CP-02', 'TYPE2', 22.00, 11.50, 'AVAILABLE');

INSERT INTO Bookings (booking_id, user_id, vehicle_id, point_id, start_at, end_at, booking_status)
VALUES
(1, 2, 1, 1, '2026-08-05 09:00:00', '2026-08-05 10:00:00', 'COMPLETED'),
(2, 3, 2, 2, '2026-08-10 11:00:00', '2026-08-10 12:00:00', 'COMPLETED'),
(3, 4, 3, 3, '2026-09-02 13:00:00', '2026-09-02 14:00:00', 'COMPLETED'),
(4, 5, 4, 4, '2026-09-12 15:00:00', '2026-09-12 16:00:00', 'COMPLETED'),
(5, 6, 5, 5, '2026-10-02 10:00:00', '2026-10-02 11:00:00', 'COMPLETED'),
(6, 7, 6, 6, '2026-10-08 14:00:00', '2026-10-08 15:00:00', 'COMPLETED'),
(7, 8, 7, 1, '2026-10-25 09:00:00', '2026-10-25 10:00:00', 'CONFIRMED'),
(8, 9, 8, 2, '2026-10-26 12:00:00', '2026-10-26 13:00:00', 'CONFIRMED');

INSERT INTO ChargingSessions (session_id, booking_id, user_id, vehicle_id, point_id, start_at, end_at, energy_kwh, tariff_per_kwh, total_cost, session_status)
VALUES
(1, 1, 2, 1, 1, '2026-08-05 09:00:00', '2026-08-05 09:45:00', 30.000, 18.00, 540.00, 'COMPLETED'),
(2, 2, 3, 2, 2, '2026-08-10 11:00:00', '2026-08-10 11:50:00', 15.000, 12.00, 180.00, 'COMPLETED'),
(3, 3, 4, 3, 3, '2026-09-02 13:00:00', '2026-09-02 13:40:00', 35.000, 20.00, 700.00, 'COMPLETED'),
(4, 4, 5, 4, 4, '2026-09-12 15:00:00', '2026-09-12 15:45:00', 20.000, 17.00, 340.00, 'COMPLETED'),
(5, 5, 6, 5, 5, '2026-10-02 10:00:00', '2026-10-02 10:40:00', 28.000, 18.50, 518.00, 'COMPLETED'),
(6, 6, 7, 6, 6, '2026-10-08 14:00:00', '2026-10-08 14:30:00', 12.000, 11.50, 138.00, 'COMPLETED');

INSERT INTO Payments (payment_id, session_id, transaction_reference, amount, payment_method, payment_status, paid_at)
VALUES
(1, 1, 'EVTXN-0001', 540.00, 'UPI', 'SUCCESS', '2026-08-05 09:50:00'),
(2, 2, 'EVTXN-0002', 180.00, 'CARD', 'SUCCESS', '2026-08-10 11:55:00'),
(3, 3, 'EVTXN-0003', 700.00, 'UPI', 'SUCCESS', '2026-09-02 13:45:00'),
(4, 4, 'EVTXN-0004', 340.00, 'WALLET', 'SUCCESS', '2026-09-12 15:50:00'),
(5, 5, 'EVTXN-0005', 518.00, 'UPI', 'SUCCESS', '2026-10-02 10:45:00'),
(6, 6, 'EVTXN-0006', 138.00, 'CARD', 'SUCCESS', '2026-10-08 14:35:00');

INSERT INTO SystemSettings (setting_key, setting_value, description) VALUES
('tax_rate_percent', '18.00', 'Goods and Services Tax (GST) rate applied to energy charging tariffs'),
('max_booking_hours', '6', 'Maximum permitted duration in hours for a single booking reservation'),
('cancellation_grace_mins', '15', 'Permitted cancellation lead time before scheduled start time in minutes'),
('min_battery_capacity_kwh', '5.0', 'Minimum supported EV battery capacity in kilowatt-hours'),
('app_currency', 'INR', 'Operational currency code for tariff display and billing calculations')
ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);

INSERT INTO AuditLogs (user_id, action, entity_name, entity_id, details, ip_address) VALUES
(1, 'SYSTEM_INIT', 'SystemSettings', NULL, 'Database initialized with 9 core normalized tables', '127.0.0.1');


-- =====================================================================
-- SECTION 5: VERIFICATION QUERIES
-- =====================================================================

SELECT 'Users' AS table_name, COUNT(*) AS total_rows FROM Users
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

SHOW TABLES;
-- =====================================================================
-- END OF SCRIPT: database/ev_charging_db.sql
-- =====================================================================
