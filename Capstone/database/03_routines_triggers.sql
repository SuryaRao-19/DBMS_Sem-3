-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 3: PROCEDURAL ROUTINES & TRIGGERS
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/03_routines_triggers.sql
-- Description: Stored procedures, deterministic functions, and business triggers
-- ============================================================

USE ev_charging_db;

-- ------------------------------------------------------------
-- 1. STORED FUNCTION: CalculateChargingCost
-- Calculates total billing amount from energy consumed and tariff rate.
-- Formula: total_cost = ROUND(p_energy_kwh * p_tariff, 2)
-- ------------------------------------------------------------
DROP FUNCTION IF EXISTS CalculateChargingCost;

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

-- ------------------------------------------------------------
-- 2. TRIGGER: trg_booking_before_insert
-- Enforces critical database-level invariants before booking creation:
-- a) End time must be strictly after start time
-- b) Vehicle must belong to the booking driver
-- c) Station and charging point must be operational ('ACTIVE' and 'AVAILABLE')
-- d) Rejects overlapping reservations for the requested charging point
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_booking_before_insert;

DELIMITER $$
CREATE TRIGGER trg_booking_before_insert
BEFORE INSERT ON Bookings
FOR EACH ROW
BEGIN
    DECLARE conflict_count INT DEFAULT 0;
    DECLARE owner_count INT DEFAULT 0;
    DECLARE point_count INT DEFAULT 0;

    -- Rule A: Valid chronological duration
    IF NEW.end_at <= NEW.start_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Booking end time must be strictly after start time.';
    END IF;

    -- Rule B: Enforce vehicle ownership by the requesting driver
    SELECT COUNT(*) INTO owner_count
    FROM Vehicles
    WHERE vehicle_id = NEW.vehicle_id
      AND user_id = NEW.user_id;

    IF owner_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Selected vehicle does not belong to the authenticated user.';
    END IF;

    -- Rule C: Verify physical station and point are operational
    SELECT COUNT(*) INTO point_count
    FROM ChargingPoints cp
    JOIN Stations s ON s.station_id = cp.station_id
    WHERE cp.point_id = NEW.point_id
      AND cp.point_status = 'AVAILABLE'
      AND s.station_status = 'ACTIVE';

    IF point_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Target charging point or station is currently unavailable.';
    END IF;

    -- Rule D: Reject conflicting/overlapping active bookings for the dispenser
    -- Interval overlap formula: (NEW.start_at < existing.end_at) AND (NEW.end_at > existing.start_at)
    SELECT COUNT(*) INTO conflict_count
    FROM Bookings
    WHERE point_id = NEW.point_id
      AND booking_status IN ('PENDING', 'CONFIRMED')
      AND (NEW.booking_id IS NULL OR booking_id <> NEW.booking_id)
      AND NEW.start_at < end_at
      AND NEW.end_at > start_at;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Charging point is already booked for this time window.';
    END IF;
END$$
DELIMITER ;

-- ------------------------------------------------------------
-- 3. STORED PROCEDURE: CompleteChargingSession
-- Atomic session completion with row-level serialization:
-- a) Locks target session row using FOR UPDATE
-- b) Validates session state is currently 'IN_PROGRESS'
-- c) Rejects negative energy consumption
-- d) Calculates final cost using CalculateChargingCost()
-- e) Updates session status to 'COMPLETED' and records end_at
-- f) Restores charging point status to 'AVAILABLE'
-- g) Employs exit handler for rollback on any SQLEXCEPTION
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS CompleteChargingSession;

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
            SET MESSAGE_TEXT = 'Energy consumed cannot be negative.';
    END IF;

    START TRANSACTION;

    SELECT tariff_per_kwh, session_status, point_id, start_at
    INTO v_tariff, v_status, v_point_id, v_start
    FROM ChargingSessions
    WHERE session_id = p_session_id
    FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Charging session not found.';
    END IF;

    IF v_status <> 'IN_PROGRESS' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Charging session is already closed or not in progress.';
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

-- ------------------------------------------------------------
-- 4. TRIGGER: trg_session_before_insert
-- Enforces:
-- a) Non-negative energy and tariff
-- b) End time cannot precede start time
-- c) Vehicle must belong to session user
-- d) Point must be currently available
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_session_before_insert;

DELIMITER $$
CREATE TRIGGER trg_session_before_insert
BEFORE INSERT ON ChargingSessions
FOR EACH ROW
BEGIN
    DECLARE v_owner_count INT DEFAULT 0;
    DECLARE v_point_count INT DEFAULT 0;

    IF NEW.energy_kwh < 0 OR NEW.tariff_per_kwh < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Energy and tariff must be non-negative.';
    END IF;

    IF NEW.end_at IS NOT NULL AND NEW.end_at < NEW.start_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Session end timestamp cannot precede start timestamp.';
    END IF;

    SELECT COUNT(*) INTO v_owner_count
    FROM Vehicles
    WHERE vehicle_id = NEW.vehicle_id
      AND user_id = NEW.user_id;

    IF v_owner_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Vehicle does not belong to the session user.';
    END IF;

    SELECT COUNT(*) INTO v_point_count
    FROM ChargingPoints
    WHERE point_id = NEW.point_id
      AND point_status = 'AVAILABLE';

    IF v_point_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Charging point is not currently available for charging.';
    END IF;
END$$
DELIMITER ;
