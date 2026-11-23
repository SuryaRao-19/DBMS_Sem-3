-- ============================================================
-- Migration 007: Google OAuth 2.0 / OIDC, Password Reset & Auth Hardening
-- Idempotent MySQL 8.0+ migration (non-destructive)
-- ============================================================

-- 1. Password Reset Tokens Table (Timed single-use SHA-256 hashed tokens)
CREATE TABLE IF NOT EXISTS PasswordResetTokens (
    token_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    used_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_prt_user (user_id, expires_at),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Extend Users Table for Google OAuth / OIDC & Lifecycle Metadata
DROP PROCEDURE IF EXISTS _apply_migration_007_upgrade;
DELIMITER $$
CREATE PROCEDURE _apply_migration_007_upgrade()
BEGIN
    -- Allow nullable password_hash for pure Google OAuth accounts
    ALTER TABLE Users
        MODIFY COLUMN password_hash VARCHAR(255) NULL;

    -- Support ADMIN, OWNER, and USER roles safely without narrowing CUSTOMER after 009
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'role'
          AND COLUMN_TYPE LIKE '%CUSTOMER%'
    ) THEN
        ALTER TABLE Users
            MODIFY COLUMN role ENUM('ADMIN', 'OWNER', 'USER') NOT NULL DEFAULT 'OWNER';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'google_sub'
    ) THEN
        ALTER TABLE Users ADD COLUMN google_sub VARCHAR(255) NULL UNIQUE AFTER password_hash;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'auth_provider'
    ) THEN
        ALTER TABLE Users ADD COLUMN auth_provider ENUM('LOCAL', 'GOOGLE', 'HYBRID') NOT NULL DEFAULT 'LOCAL' AFTER google_sub;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'email_verified'
    ) THEN
        ALTER TABLE Users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 0 AFTER auth_provider;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'profile_picture_url'
    ) THEN
        ALTER TABLE Users ADD COLUMN profile_picture_url VARCHAR(500) NULL AFTER email_verified;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'updated_at'
    ) THEN
        ALTER TABLE Users ADD COLUMN updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'last_login'
    ) THEN
        ALTER TABLE Users ADD COLUMN last_login DATETIME NULL AFTER updated_at;
    END IF;
END$$
DELIMITER ;

CALL _apply_migration_007_upgrade();
DROP PROCEDURE IF EXISTS _apply_migration_007_upgrade;

