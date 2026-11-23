-- ============================================================
-- Migration 009: Multi-Role Customer Portal, Vehicles Upgrade,
-- Saved Stations, Notifications, Owner Onboarding & Ownership FK
-- Idempotent MySQL 8.0+ migration (non-destructive)
-- ============================================================

-- 1. Expand Users.role ENUM cleanly and map legacy driver rows ('USER' / pre-upgrade driver accounts) to 'CUSTOMER'
ALTER TABLE Users
    MODIFY COLUMN role ENUM('CUSTOMER', 'OWNER', 'USER', 'ADMIN') NOT NULL DEFAULT 'CUSTOMER';

-- Convert any existing 'USER' role rows to 'CUSTOMER'
UPDATE Users SET role = 'CUSTOMER' WHERE role = 'USER';

-- Convert pre-existing non-admin EV driver accounts (seed drivers 2..11 & demo.customer01@example.test)
-- cleanly to CUSTOMER while leaving any future/real station OWNER records untouched on repeated runs
UPDATE Users u
SET u.role = 'CUSTOMER'
WHERE u.role = 'OWNER'
  AND u.user_id IN (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
  AND u.email <> 'owner.station01@example.test';

UPDATE Users
SET role = 'CUSTOMER'
WHERE role = 'OWNER'
  AND email = 'demo.customer01@example.test';

-- 2. SavedStations Table (Customer Bookmarks)
CREATE TABLE IF NOT EXISTS SavedStations (
    saved_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    station_id INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_saved_user_station (user_id, station_id),
    INDEX idx_saved_user (user_id),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES Stations(station_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Notifications Table (Bookings, Payments, Owner Onboarding)
CREATE TABLE IF NOT EXISTS Notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(160) NOT NULL,
    message TEXT NOT NULL,
    category ENUM('BOOKING', 'PAYMENT', 'SYSTEM', 'OWNER_APPLICATION') NOT NULL DEFAULT 'SYSTEM',
    link_url VARCHAR(255) NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notif_user_read (user_id, is_read, created_at),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. OwnerApplications Table (Station Partner Onboarding Workflow)
CREATE TABLE IF NOT EXISTS OwnerApplications (
    application_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    applicant_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(30) NULL,
    company_name VARCHAR(150) NULL,
    station_name VARCHAR(150) NOT NULL,
    city VARCHAR(80) NOT NULL,
    state VARCHAR(80) NULL,
    pincode VARCHAR(20) NULL,
    proposed_chargers INT NOT NULL DEFAULT 1,
    power_capacity_kw DECIMAL(8,2) NOT NULL DEFAULT 30.00,
    application_status ENUM('PENDING', 'APPROVED', 'REJECTED') NOT NULL DEFAULT 'PENDING',
    reviewed_by_user_id INT NULL,
    admin_notes VARCHAR(500) NULL,
    reviewed_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_owner_app_status (application_status, created_at),
    INDEX idx_owner_app_user (user_id),
    INDEX idx_owner_app_email (email),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (reviewed_by_user_id) REFERENCES Users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Alter Vehicles, Stations, and Bookings safely
DROP PROCEDURE IF EXISTS _apply_migration_009_upgrade;
DELIMITER $$
CREATE PROCEDURE _apply_migration_009_upgrade()
BEGIN
    -- Vehicles richer EV metadata
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Vehicles' AND COLUMN_NAME = 'vehicle_category'
    ) THEN
        ALTER TABLE Vehicles
            ADD COLUMN vehicle_category ENUM('2W', '3W', '4W_SUV', '4W_SEDAN', 'FLEET_BUS', 'COMMERCIAL') NOT NULL DEFAULT '4W_SUV' AFTER model;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Vehicles' AND COLUMN_NAME = 'connector_type'
    ) THEN
        ALTER TABLE Vehicles
            ADD COLUMN connector_type ENUM('TYPE2', 'CCS2', 'CHADEMO', 'GB_T') NOT NULL DEFAULT 'CCS2' AFTER vehicle_category;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Vehicles' AND COLUMN_NAME = 'registration_year'
    ) THEN
        ALTER TABLE Vehicles
            ADD COLUMN registration_year INT NULL AFTER battery_capacity_kwh;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Vehicles' AND COLUMN_NAME = 'is_default'
    ) THEN
        ALTER TABLE Vehicles
            ADD COLUMN is_default TINYINT(1) NOT NULL DEFAULT 0 AFTER registration_year;
    END IF;

    -- Stations explicit Station Owner FK
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'owner_user_id'
    ) THEN
        ALTER TABLE Stations ADD COLUMN owner_user_id INT NULL AFTER operator_name;
        ALTER TABLE Stations ADD INDEX idx_stations_owner (owner_user_id);
        ALTER TABLE Stations ADD CONSTRAINT fk_stations_owner FOREIGN KEY (owner_user_id) REFERENCES Users(user_id) ON DELETE SET NULL;
    END IF;

    -- Bookings estimated telemetry columns
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Bookings' AND COLUMN_NAME = 'estimated_energy_kwh'
    ) THEN
        ALTER TABLE Bookings ADD COLUMN estimated_energy_kwh DECIMAL(8,2) NULL AFTER end_at;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Bookings' AND COLUMN_NAME = 'estimated_cost'
    ) THEN
        ALTER TABLE Bookings ADD COLUMN estimated_cost DECIMAL(10,2) NULL AFTER estimated_energy_kwh;
    END IF;
END$$
DELIMITER ;

CALL _apply_migration_009_upgrade();
DROP PROCEDURE IF EXISTS _apply_migration_009_upgrade;

-- 6. Mark the first vehicle of any customer without a default as their default vehicle
UPDATE Vehicles v
JOIN (
    SELECT user_id, MIN(vehicle_id) AS first_vid
    FROM Vehicles
    GROUP BY user_id
    HAVING SUM(is_default) = 0
) first_v ON first_v.first_vid = v.vehicle_id
SET v.is_default = 1;

-- 7. Ensure a dedicated demo Station Owner account exists for Station Partner portal testing
INSERT INTO Users (full_name, email, phone, password_hash, role, account_status, auth_provider, email_verified, is_demo)
VALUES (
    'Station Partner Demo 01',
    'owner.station01@example.test',
    '+91-9000000101',
    'scrypt:32768:8:1$wEFljUOpHWp5xLru$b370031fe305de228a3266dfaf1fb203a5e4d395e0ff86fb2eb040f9a3661540f0891c563af46dac3b63667aa266a15f42ba9fcb4fb5a5ee10ffbb5273fd4b76',
    'OWNER',
    'ACTIVE',
    'LOCAL',
    1,
    1
)
ON DUPLICATE KEY UPDATE
    password_hash = VALUES(password_hash),
    role = 'OWNER',
    account_status = 'ACTIVE';

-- Assign up to 2 demonstration stations (if unassigned) to demo Station Partner so owner dashboard has real scoped data
UPDATE Stations s
JOIN (
    SELECT station_id FROM Stations WHERE provenance_category = 'C_LOCAL_DEMO' ORDER BY station_id LIMIT 2
) pick ON pick.station_id = s.station_id
JOIN Users u ON u.email = 'owner.station01@example.test'
SET s.owner_user_id = u.user_id
WHERE s.owner_user_id IS NULL;
