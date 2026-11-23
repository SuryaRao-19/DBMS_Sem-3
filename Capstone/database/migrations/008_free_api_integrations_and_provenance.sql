-- ============================================================
-- Migration 008: Free Public API Integrations, Caching,
-- Extended QR Architecture (Point + Booking QRs) & 4-Way Provenance
-- Idempotent MySQL 8.0+ migration (non-destructive)
-- ============================================================

-- 1. Persistent API Response Cache (Serverless & Multi-Worker Safe)
CREATE TABLE IF NOT EXISTS ApiCache (
    cache_key VARCHAR(160) PRIMARY KEY,
    provider VARCHAR(60) NOT NULL,
    payload_json LONGTEXT NOT NULL,
    fetched_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX idx_api_cache_provider_exp (provider, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. API Integration Observability & Audit Telemetry
CREATE TABLE IF NOT EXISTS ApiIntegrationLogs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(60) NOT NULL,
    operation VARCHAR(80) NOT NULL,
    status ENUM('SUCCESS', 'SKIPPED_UNCONFIGURED', 'FAILED', 'RATE_LIMITED') NOT NULL,
    http_status INT NULL,
    records_fetched INT NOT NULL DEFAULT 0,
    records_imported INT NOT NULL DEFAULT 0,
    duplicates_detected INT NOT NULL DEFAULT 0,
    latency_ms INT NULL,
    error_message VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_api_logs_provider_created (provider, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Charging Point (Dispenser) Identification QR Codes
CREATE TABLE IF NOT EXISTS PointQRCodes (
    qr_id INT AUTO_INCREMENT PRIMARY KEY,
    point_id INT NOT NULL,
    qr_token VARCHAR(64) NOT NULL UNIQUE,
    qr_status ENUM('ACTIVE', 'REVOKED') NOT NULL DEFAULT 'ACTIVE',
    scan_count INT NOT NULL DEFAULT 0,
    last_scanned_at DATETIME NULL,
    created_by INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME NULL,
    INDEX idx_point_qr_point (point_id, qr_status),
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Booking Check-In Verification QR Codes
CREATE TABLE IF NOT EXISTS BookingQRCodes (
    qr_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL UNIQUE,
    qr_token VARCHAR(64) NOT NULL UNIQUE,
    qr_status ENUM('ACTIVE', 'USED', 'REVOKED') NOT NULL DEFAULT 'ACTIVE',
    verified_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_booking_qr_status (qr_status),
    FOREIGN KEY (booking_id) REFERENCES Bookings(booking_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Alter Stations & DataSources with Full External Provenance + 4-Way Category
DROP PROCEDURE IF EXISTS _apply_migration_008_upgrade;
DELIMITER $$
CREATE PROCEDURE _apply_migration_008_upgrade()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'external_source_id'
    ) THEN
        ALTER TABLE Stations ADD COLUMN external_source_id VARCHAR(120) NULL AFTER source_name;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'license_info'
    ) THEN
        ALTER TABLE Stations ADD COLUMN license_info VARCHAR(255) NULL AFTER external_source_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'provenance_category'
    ) THEN
        ALTER TABLE Stations ADD COLUMN provenance_category ENUM(
            'A_OFFICIAL_DISCLOSURE',
            'B_THIRD_PARTY_API',
            'C_LOCAL_DEMO',
            'D_SIMULATED_TELEMETRY'
        ) NOT NULL DEFAULT 'A_OFFICIAL_DISCLOSURE' AFTER record_origin;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'imported_at'
    ) THEN
        ALTER TABLE Stations ADD COLUMN imported_at DATETIME NULL AFTER retrieved_at;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'last_synced_at'
    ) THEN
        ALTER TABLE Stations ADD COLUMN last_synced_at DATETIME NULL AFTER imported_at;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'raw_payload_hash'
    ) THEN
        ALTER TABLE Stations ADD COLUMN raw_payload_hash CHAR(64) NULL AFTER last_synced_at;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND INDEX_NAME = 'uq_station_external_source'
    ) THEN
        ALTER TABLE Stations ADD UNIQUE KEY uq_station_external_source (source_name, external_source_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'provenance_category'
    ) THEN
        ALTER TABLE DataSources ADD COLUMN provenance_category ENUM(
            'A_OFFICIAL_DISCLOSURE',
            'B_THIRD_PARTY_API',
            'C_LOCAL_DEMO',
            'D_SIMULATED_TELEMETRY'
        ) NOT NULL DEFAULT 'A_OFFICIAL_DISCLOSURE' AFTER record_origin;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'license_info'
    ) THEN
        ALTER TABLE DataSources ADD COLUMN license_info VARCHAR(255) NULL AFTER provenance_category;
    END IF;
END$$
DELIMITER ;

CALL _apply_migration_008_upgrade();
DROP PROCEDURE IF EXISTS _apply_migration_008_upgrade;

-- 6. Classify Existing Station & DataSource Records Cleanly Across Categories A / B / C / D
UPDATE Stations
SET provenance_category = CASE
    WHEN is_demo = 1 OR record_origin = 'DEMONSTRATION_SEED' THEN 'C_LOCAL_DEMO'
    WHEN record_origin = 'GOOGLE_PLACES_REFERENCE' OR source_name LIKE '%Open Charge Map%' THEN 'B_THIRD_PARTY_API'
    ELSE 'A_OFFICIAL_DISCLOSURE'
END,
imported_at = COALESCE(imported_at, retrieved_at, created_at);

UPDATE DataSources
SET provenance_category = CASE
    WHEN record_origin = 'DEMONSTRATION_SEED' OR data_status = 'DEMO' THEN 'C_LOCAL_DEMO'
    WHEN record_origin IN ('VERIFIED_PUBLIC_SOURCE', 'GOOGLE_PLACES_REFERENCE') AND source_name NOT LIKE '%Tata Power%' THEN 'B_THIRD_PARTY_API'
    ELSE 'A_OFFICIAL_DISCLOSURE'
END;

-- 7. Seed Initial ACTIVE Dispenser QRs & Booking QRs for Existing Records
INSERT INTO PointQRCodes (point_id, qr_token, qr_status, scan_count)
SELECT cp.point_id, LOWER(REPLACE(UUID(), '-', '')), 'ACTIVE', 0
FROM ChargingPoints cp
LEFT JOIN PointQRCodes pq ON pq.point_id = cp.point_id AND pq.qr_status = 'ACTIVE'
WHERE pq.qr_id IS NULL;

INSERT INTO BookingQRCodes (booking_id, qr_token, qr_status)
SELECT b.booking_id, LOWER(REPLACE(UUID(), '-', '')), 'ACTIVE'
FROM Bookings b
LEFT JOIN BookingQRCodes bq ON bq.booking_id = b.booking_id
WHERE bq.qr_id IS NULL;

-- 8. Seed Free API Provenance Entries in DataSources (Categories B & D)
INSERT INTO DataSources (
    data_item, category, source_name, source_type, source_url, published_at, retrieved_at,
    verification_date, data_status, confidence_level, record_origin, provenance_category,
    license_info, associated_record_count, notes
) VALUES
(
    'Open Charge Map Public EV POI Directory (API v3)',
    'Third-Party Charging API',
    'Open Charge Map',
    'REST_API_V3',
    'https://openchargemap.org/site/develop/api',
    NULL, NOW(), CURDATE(), 'VERIFIED', 'MEDIUM', 'VERIFIED_PUBLIC_SOURCE', 'B_THIRD_PARTY_API',
    'CC BY 4.0 (Open Charge Map Contributors)',
    0,
    'Requires free OPEN_CHARGE_MAP_API_KEY via X-API-Key header. Supplies static POI metadata; does not claim live charger occupancy unless explicitly provided.'
),
(
    'OpenStreetMap Tiles & Nominatim Geocoding / Reverse Geocoding',
    'Maps & Geocoding',
    'OpenStreetMap Foundation / Nominatim',
    'PUBLIC_GEOCODING_API',
    'https://nominatim.openstreetmap.org/',
    NULL, NOW(), CURDATE(), 'VERIFIED', 'HIGH', 'VERIFIED_PUBLIC_SOURCE', 'B_THIRD_PARTY_API',
    'ODbL 1.0 (© OpenStreetMap contributors)',
    0,
    'Used via Leaflet map tiles and explicit-submit address lookup / reverse geocoding (strict 1 req/sec throttle + MySQL cache; never keystroke autocomplete).'
),
(
    'OSRM Driving Route & Distance Matrix Service',
    'Navigation & Routing',
    'Project OSRM Demo Server',
    'ROUTING_API',
    'https://router.project-osrm.org/',
    NULL, NOW(), CURDATE(), 'VERIFIED', 'MEDIUM', 'VERIFIED_PUBLIC_SOURCE', 'B_THIRD_PARTY_API',
    'BSD 2-Clause / ODbL OSM road network (Best-effort demo API)',
    0,
    'Provides driving geometry polylines, road distance, and ETA between user coordinates and charging stations, with automatic Haversine fallback on timeout.'
),
(
    'Open-Meteo Weather Forecast & Live Conditions',
    'Weather Telemetry',
    'Open-Meteo',
    'WEATHER_API',
    'https://open-meteo.com/',
    NULL, NOW(), CURDATE(), 'VERIFIED', 'HIGH', 'VERIFIED_PUBLIC_SOURCE', 'B_THIRD_PARTY_API',
    'CC BY 4.0 (Weather data by Open-Meteo.com)',
    0,
    'Provides station-coordinate temperature, precipitation probability, wind speed, and short hourly forecast without API keys; cached 30 min in MySQL.'
),
(
    'India Postal PIN Code Directory Lookup',
    'Postal & Address Validation',
    'PostalPinCode.in (India Post Reference)',
    'PINCODE_API',
    'https://api.postalpincode.in/',
    NULL, NOW(), CURDATE(), 'VERIFIED', 'MEDIUM', 'VERIFIED_PUBLIC_SOURCE', 'B_THIRD_PARTY_API',
    'Public Indian PIN Lookup Reference (Non-exclusive 1-to-many Post Offices)',
    0,
    'Validates 6-digit Indian PIN codes and returns State, District, and all associated Post Office localities (never assuming 1 PIN = 1 physical street address).'
),
(
    'Simulated Charging Meter Telemetry & Razorpay Sandbox Checkout',
    'Portal Telemetry & Sandbox Payments',
    'EZ Charge Portal Simulation Engine',
    'SYSTEM_SIMULATION',
    NULL, NULL, NOW(), CURDATE(), 'DEMO', 'HIGH', 'SYSTEM_GENERATED', 'D_SIMULATED_TELEMETRY',
    'Internal Academic Simulation (Test Mode Only)',
    0,
    'All kWh energy delivery counters, billing estimates, and Razorpay TEST MODE payment orders are simulated academic workflows, never live utility metering or live money.'
)
ON DUPLICATE KEY UPDATE
    category = VALUES(category),
    source_type = VALUES(source_type),
    provenance_category = VALUES(provenance_category),
    license_info = VALUES(license_info),
    notes = VALUES(notes),
    retrieved_at = NOW();

