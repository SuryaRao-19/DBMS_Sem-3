-- ============================================================
-- MIGRATION 002: Add AuditLogs and SystemSettings Tables
-- Database: MySQL 8.0+
-- File: database/09_migrations/002_add_audit_logs_and_settings.sql
-- ============================================================

USE ev_charging_db;

-- 1. Create AuditLogs Table
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

-- 2. Create SystemSettings Table
CREATE TABLE IF NOT EXISTS SystemSettings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    description VARCHAR(255) NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Seed Default System Settings (using INSERT IGNORE for idempotency)
INSERT IGNORE INTO SystemSettings (setting_key, setting_value, description) VALUES
('tax_rate_percent', '18.00', 'Goods and Services Tax (GST) rate applied to energy charging tariffs'),
('max_booking_hours', '6', 'Maximum permitted duration in hours for a single booking reservation'),
('cancellation_grace_mins', '15', 'Permitted cancellation lead time before scheduled start time in minutes'),
('min_battery_capacity_kwh', '5.0', 'Minimum supported EV battery capacity in kilowatt-hours'),
('app_currency', 'INR', 'Operational currency code for tariff display and billing calculations');

-- 4. Verification statement
SELECT 'Migration 002 executed successfully: AuditLogs & SystemSettings ready.' AS migration_status;
