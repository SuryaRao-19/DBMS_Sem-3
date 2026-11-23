-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 2: CONSTRAINTS & INDEXES
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/02_constraints_indexes.sql
-- Description: Applies composite B-Tree indexes idempotently
-- ============================================================

USE ev_charging_db;

-- ------------------------------------------------------------
-- IDEMPOTENT INDEX CREATION HELPER
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS CreateIndexIfNotExists;

DELIMITER $$
CREATE PROCEDURE CreateIndexIfNotExists(
    IN p_table VARCHAR(64),
    IN p_index VARCHAR(64),
    IN p_columns VARCHAR(255)
)
BEGIN
    DECLARE idx_exists INT DEFAULT 0;
    SELECT COUNT(*) INTO idx_exists
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() 
      AND TABLE_NAME = p_table 
      AND INDEX_NAME = p_index;

    IF idx_exists = 0 THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table, '` ADD INDEX `', p_index, '` (', p_columns, ')');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- ------------------------------------------------------------
-- COMPOSITE & COVERING B-TREE INDEXES FOR OPTIMIZED RETRIEVAL
-- ------------------------------------------------------------

-- 1. Stations Table Indexes (City & status search)
CALL CreateIndexIfNotExists('Stations', 'idx_stations_city_status', 'city, station_status');

-- 2. ChargingPoints Table Indexes (Dispenser lookup per station)
CALL CreateIndexIfNotExists('ChargingPoints', 'idx_cp_station_status', 'station_id, point_status');

-- 3. Bookings Table Indexes (CRITICAL: Collision detection & user status queries)
CALL CreateIndexIfNotExists('Bookings', 'idx_booking_point_time', 'point_id, start_at, end_at');
CALL CreateIndexIfNotExists('Bookings', 'idx_booking_user_status', 'user_id, booking_status');

-- 4. ChargingSessions Table Indexes (Driver history & dispenser analytics)
CALL CreateIndexIfNotExists('ChargingSessions', 'idx_session_user_date', 'user_id, start_at');
CALL CreateIndexIfNotExists('ChargingSessions', 'idx_session_point_date', 'point_id, start_at');

-- 5. Payments Table Indexes (Status and settlement reconciliation)
CALL CreateIndexIfNotExists('Payments', 'idx_payment_status_date', 'payment_status, paid_at');

-- 6. AuditLogs Table Indexes (Audit trail lookups)
CALL CreateIndexIfNotExists('AuditLogs', 'idx_audit_entity', 'entity_name, entity_id');
CALL CreateIndexIfNotExists('AuditLogs', 'idx_audit_created', 'created_at');

-- Clean up helper procedure
DROP PROCEDURE IF EXISTS CreateIndexIfNotExists;

-- ------------------------------------------------------------
-- VERIFICATION OF ACTIVE INDEXES
-- ------------------------------------------------------------
SELECT 
    TABLE_NAME, 
    INDEX_NAME, 
    NON_UNIQUE, 
    COLUMN_NAME, 
    SEQ_IN_INDEX, 
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'ev_charging_db'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
