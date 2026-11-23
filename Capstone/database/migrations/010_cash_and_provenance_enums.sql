-- ============================================================
-- Migration 010: Cash Collection & Provenance Support
-- Idempotent MySQL 8.0+ migration (non-destructive)
-- ============================================================

DROP PROCEDURE IF EXISTS _apply_migration_010_cash_and_provenance;
DELIMITER $$
CREATE PROCEDURE _apply_migration_010_cash_and_provenance()
BEGIN
    -- 1. Payments cash collection tracking columns
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'cash_collected_by'
    ) THEN
        ALTER TABLE Payments ADD COLUMN cash_collected_by INT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'cash_collected_at'
    ) THEN
        ALTER TABLE Payments ADD COLUMN cash_collected_at DATETIME NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'cash_notes'
    ) THEN
        ALTER TABLE Payments ADD COLUMN cash_notes VARCHAR(255) NULL;
    END IF;

    -- 2. Expand Payments payment_status ENUM to include PAYMENT_DUE
    ALTER TABLE Payments MODIFY COLUMN payment_status 
        ENUM('CREATED','PENDING','AUTHORIZED','CAPTURED','SUCCESS','FAILED','EXPIRED','REFUNDED','PAYMENT_DUE') 
        NOT NULL DEFAULT 'PENDING';

    -- 3. Expand Bookings booking_status ENUM to include PENDING_PAYMENT, EXPIRED
    ALTER TABLE Bookings MODIFY COLUMN booking_status 
        ENUM('PENDING','PENDING_PAYMENT','CONFIRMED','CANCELLED','COMPLETED','EXPIRED') 
        NOT NULL DEFAULT 'CONFIRMED';
END$$
DELIMITER ;

CALL _apply_migration_010_cash_and_provenance();
DROP PROCEDURE IF EXISTS _apply_migration_010_cash_and_provenance;
