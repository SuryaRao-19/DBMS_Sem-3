-- ============================================================
-- MIGRATION 003: Add ContactMessages Table for Web3Forms Enquiries
-- Database: MySQL 8.0+
-- File: database/09_migrations/003_add_contact_messages.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS ContactMessages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(25) NULL,
    subject VARCHAR(200) NOT NULL,
    category VARCHAR(60) NOT NULL,
    message TEXT NOT NULL,
    submission_status ENUM('NEW', 'IN_PROGRESS', 'RESOLVED') NOT NULL DEFAULT 'NEW',
    email_delivery_status ENUM('PENDING', 'SENT', 'FAILED') NOT NULL DEFAULT 'PENDING',
    email_error VARCHAR(255) NULL,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_contact_status_created (submission_status, created_at),
    INDEX idx_contact_email_created (email, created_at),
    INDEX idx_contact_ip_created (ip_address, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

