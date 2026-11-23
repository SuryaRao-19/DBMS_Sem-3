-- ============================================================
-- Migration 005: Razorpay Test Mode, Webhooks & Official Stats Sync
-- Idempotent MySQL 8.0+ migration (non-destructive)
-- ============================================================

-- 1. Webhook Idempotency & Audit Trail Table
CREATE TABLE IF NOT EXISTS PaymentWebhookEvents (
    webhook_id INT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(120) NOT NULL UNIQUE,
    event_type VARCHAR(80) NOT NULL,
    razorpay_order_id VARCHAR(100) NULL,
    razorpay_payment_id VARCHAR(100) NULL,
    signature_verified TINYINT(1) NOT NULL DEFAULT 0,
    processing_status ENUM('PROCESSED', 'DUPLICATE_IGNORED', 'FAILED') NOT NULL DEFAULT 'PROCESSED',
    payload_summary TEXT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_webhook_order (razorpay_order_id),
    INDEX idx_webhook_type_time (event_type, received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Extend Payments Table Safely for Razorpay Test Orders & Tax Breakdown
DROP PROCEDURE IF EXISTS _apply_migration_005_razorpay;
DELIMITER $$
CREATE PROCEDURE _apply_migration_005_razorpay()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'gateway_provider') THEN
        ALTER TABLE Payments ADD COLUMN gateway_provider ENUM('RAZORPAY_TEST', 'DEMO_LEDGER') NOT NULL DEFAULT 'DEMO_LEDGER' AFTER payment_method;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'razorpay_order_id') THEN
        ALTER TABLE Payments ADD COLUMN razorpay_order_id VARCHAR(100) NULL AFTER transaction_reference;
        ALTER TABLE Payments ADD INDEX idx_payments_rzp_order (razorpay_order_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'razorpay_payment_id') THEN
        ALTER TABLE Payments ADD COLUMN razorpay_payment_id VARCHAR(100) NULL AFTER razorpay_order_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'razorpay_signature') THEN
        ALTER TABLE Payments ADD COLUMN razorpay_signature VARCHAR(255) NULL AFTER razorpay_payment_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'base_amount') THEN
        ALTER TABLE Payments ADD COLUMN base_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00 AFTER amount;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'tax_amount') THEN
        ALTER TABLE Payments ADD COLUMN tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00 AFTER base_amount;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'currency') THEN
        ALTER TABLE Payments ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'INR' AFTER tax_amount;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NetworkOperators' AND COLUMN_NAME = 'play_store_url') THEN
        ALTER TABLE NetworkOperators ADD COLUMN play_store_url VARCHAR(500) NULL AFTER official_website;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NetworkOperators' AND COLUMN_NAME = 'linktree_url') THEN
        ALTER TABLE NetworkOperators ADD COLUMN linktree_url VARCHAR(500) NULL AFTER play_store_url;
    END IF;
END$$
DELIMITER ;

CALL _apply_migration_005_razorpay();
DROP PROCEDURE IF EXISTS _apply_migration_005_razorpay;

-- 3. Update Verified Official Tata Power EZ Charge Statistics, Play Store & Linktree
UPDATE NetworkOperators SET
    play_store_url = 'https://play.google.com/store/apps/details?id=com.tatapower.ezcharge',
    linktree_url = 'https://linktr.ee/Tata_Power_EZ_Charge',
    network_scale_summary = '5,500+ public charging points, 1.2 lakh+ home chargers, and 1,200+ e-bus charging points across 620+/700+ cities & towns in India',
    last_verified_at = NOW()
WHERE operator_name = 'Tata Power EZ Charge';

-- 4. Seed / Update Verified Statistics & Tariff Entries in DataSources
INSERT INTO DataSources (data_item, source_name, source_url, verification_date, data_status, notes) VALUES
('Tata Power EZ Charge Scale (5,500+ public points, 620+ cities, 1.2L+ home chargers, 1,200+ bus points)', 'Tata Power Official EZ Charge Portal', 'https://www.tatapower.com/ezcharge/', '2026-11-12', 'VERIFIED', 'Published network milestones across public, residential, and municipal e-bus depot corridors.'),
('Tata Power EZ Charge Official Mobile App & Linktree Directory', 'Google Play Store & Official Linktree', 'https://linktr.ee/Tata_Power_EZ_Charge', '2026-11-12', 'VERIFIED', 'Official EZ Charge Android app (com.tatapower.ezcharge) and social profile directory.'),
('Public EV Charging Tariffs (Dynamic DISCOM & Site Rates)', 'Tata Power EZ Charge App / Delhi EV Benchmarks', 'https://www.tatapower.com/ezcharge/', '2026-11-12', 'ESTIMATED', 'Tata Power uses dynamic site-specific tariffs inside its app (typical India public rates: Rs. 8-15/kWh AC, Rs. 15-25+/kWh DC fast). Demo bay tariffs are illustrative.')
ON DUPLICATE KEY UPDATE
    source_name = VALUES(source_name),
    source_url = VALUES(source_url),
    verification_date = VALUES(verification_date),
    data_status = VALUES(data_status),
    notes = VALUES(notes);

