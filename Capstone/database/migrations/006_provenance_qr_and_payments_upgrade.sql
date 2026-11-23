-- ============================================================
-- Migration 006: Provenance Fields, Candidate Stations,
-- Station Identification QRs, Dynamic Payment QRs & Synthetic Seed
-- Idempotent MySQL 8.0+ migration (non-destructive)
-- ============================================================

-- 1. Station Identification QR Table (Distinct from Payment QR)
CREATE TABLE IF NOT EXISTS StationQRCodes (
    qr_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    qr_token VARCHAR(64) NOT NULL UNIQUE,
    qr_status ENUM('ACTIVE', 'REVOKED') NOT NULL DEFAULT 'ACTIVE',
    expires_at DATETIME NULL,
    scan_count INT NOT NULL DEFAULT 0,
    last_scanned_at DATETIME NULL,
    created_by INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME NULL,
    INDEX idx_station_qr_station (station_id, qr_status),
    FOREIGN KEY (station_id) REFERENCES Stations(station_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Provenance, QR, & Payment Lifecycle Columns
DROP PROCEDURE IF EXISTS _apply_migration_006_upgrade;
DELIMITER $$
CREATE PROCEDURE _apply_migration_006_upgrade()
BEGIN
    -- Stations metadata & provenance
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'station_slug') THEN
        ALTER TABLE Stations ADD COLUMN station_slug VARCHAR(160) NULL UNIQUE AFTER station_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'locality') THEN
        ALTER TABLE Stations ADD COLUMN locality VARCHAR(120) NULL AFTER address;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'country') THEN
        ALTER TABLE Stations ADD COLUMN country VARCHAR(60) NOT NULL DEFAULT 'India' AFTER postal_code;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'charger_type') THEN
        ALTER TABLE Stations ADD COLUMN charger_type VARCHAR(80) NULL AFTER charger_capacity_kw;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'gun_count') THEN
        ALTER TABLE Stations ADD COLUMN gun_count INT NULL AFTER charger_type;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'source_type') THEN
        ALTER TABLE Stations ADD COLUMN source_type VARCHAR(60) NULL AFTER source_url;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'source_name') THEN
        ALTER TABLE Stations ADD COLUMN source_name VARCHAR(160) NULL AFTER source_type;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'published_at') THEN
        ALTER TABLE Stations ADD COLUMN published_at DATE NULL AFTER source_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'retrieved_at') THEN
        ALTER TABLE Stations ADD COLUMN retrieved_at DATETIME NULL AFTER published_at;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'confidence_level') THEN
        ALTER TABLE Stations ADD COLUMN confidence_level ENUM('HIGH', 'MEDIUM', 'LOW') NOT NULL DEFAULT 'MEDIUM' AFTER retrieved_at;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'record_origin') THEN
        ALTER TABLE Stations ADD COLUMN record_origin ENUM('OFFICIAL_COMPANY_SOURCE', 'VERIFIED_PUBLIC_SOURCE', 'GOOGLE_PLACES_REFERENCE', 'DEMONSTRATION_SEED', 'USER_SUBMITTED', 'SYSTEM_GENERATED') NOT NULL DEFAULT 'VERIFIED_PUBLIC_SOURCE' AFTER confidence_level;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Stations' AND COLUMN_NAME = 'is_demo') THEN
        ALTER TABLE Stations ADD COLUMN is_demo TINYINT(1) NOT NULL DEFAULT 0 AFTER record_origin;
    END IF;

    ALTER TABLE Stations
        MODIFY COLUMN verification_status ENUM('VERIFIED', 'PENDING_VERIFICATION', 'PENDING_REVIEW', 'HISTORICAL', 'DEMO', 'ESTIMATED', 'UNAVAILABLE', 'OUTDATED') NOT NULL DEFAULT 'DEMO';

    -- DataSources richer provenance
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'category') THEN
        ALTER TABLE DataSources ADD COLUMN category VARCHAR(80) NOT NULL DEFAULT 'Company Reference' AFTER data_item;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'source_type') THEN
        ALTER TABLE DataSources ADD COLUMN source_type VARCHAR(60) NULL AFTER source_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'published_at') THEN
        ALTER TABLE DataSources ADD COLUMN published_at DATE NULL AFTER source_url;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'retrieved_at') THEN
        ALTER TABLE DataSources ADD COLUMN retrieved_at DATETIME NULL AFTER published_at;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'confidence_level') THEN
        ALTER TABLE DataSources ADD COLUMN confidence_level ENUM('HIGH', 'MEDIUM', 'LOW') NOT NULL DEFAULT 'HIGH' AFTER data_status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'record_origin') THEN
        ALTER TABLE DataSources ADD COLUMN record_origin ENUM('OFFICIAL_COMPANY_SOURCE', 'VERIFIED_PUBLIC_SOURCE', 'GOOGLE_PLACES_REFERENCE', 'DEMONSTRATION_SEED', 'USER_SUBMITTED', 'SYSTEM_GENERATED') NOT NULL DEFAULT 'OFFICIAL_COMPANY_SOURCE' AFTER confidence_level;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'DataSources' AND COLUMN_NAME = 'associated_record_count') THEN
        ALTER TABLE DataSources ADD COLUMN associated_record_count INT NOT NULL DEFAULT 0 AFTER record_origin;
    END IF;

    ALTER TABLE DataSources
        MODIFY COLUMN data_status ENUM('VERIFIED', 'PENDING_VERIFICATION', 'HISTORICAL', 'DEMO', 'ESTIMATED', 'UNAVAILABLE', 'OUTDATED') NOT NULL DEFAULT 'VERIFIED';

    -- NetworkOperators App Store URL
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NetworkOperators' AND COLUMN_NAME = 'app_store_url') THEN
        ALTER TABLE NetworkOperators ADD COLUMN app_store_url VARCHAR(500) NULL AFTER play_store_url;
    END IF;

    -- Payments Razorpay lifecycle statuses & dynamic payment QR expiry fields
    ALTER TABLE Payments
        MODIFY COLUMN payment_status ENUM('CREATED', 'PENDING', 'AUTHORIZED', 'CAPTURED', 'SUCCESS', 'FAILED', 'EXPIRED', 'REFUNDED') NOT NULL DEFAULT 'PENDING';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'payment_qr_id') THEN
        ALTER TABLE Payments ADD COLUMN payment_qr_id VARCHAR(120) NULL AFTER razorpay_signature;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'payment_qr_payload') THEN
        ALTER TABLE Payments ADD COLUMN payment_qr_payload TEXT NULL AFTER payment_qr_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Payments' AND COLUMN_NAME = 'qr_expires_at') THEN
        ALTER TABLE Payments ADD COLUMN qr_expires_at DATETIME NULL AFTER payment_qr_payload;
    END IF;

    -- Demo vs Live data origin tagging across operational tables
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Users' AND COLUMN_NAME = 'is_demo') THEN
        ALTER TABLE Users ADD COLUMN is_demo TINYINT(1) NOT NULL DEFAULT 0 AFTER account_status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Bookings' AND COLUMN_NAME = 'is_demo') THEN
        ALTER TABLE Bookings ADD COLUMN is_demo TINYINT(1) NOT NULL DEFAULT 0 AFTER booking_status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ChargingSessions' AND COLUMN_NAME = 'is_demo') THEN
        ALTER TABLE ChargingSessions ADD COLUMN is_demo TINYINT(1) NOT NULL DEFAULT 0 AFTER session_status;
    END IF;
END$$
DELIMITER ;

CALL _apply_migration_006_upgrade();
DROP PROCEDURE IF EXISTS _apply_migration_006_upgrade;

-- 3. Backfill slugs and provenance metadata on existing verified NCR stations
UPDATE Stations
SET station_slug = LOWER(
        TRIM(BOTH '-' FROM REGEXP_REPLACE(REGEXP_REPLACE(station_name, '[^a-zA-Z0-9]+', '-'), '-+', '-'))
    ),
    source_type = COALESCE(source_type, 'OFFICIAL_PORTAL_AND_PUBLIC_LOCATOR'),
    source_name = COALESCE(source_name, 'Tata Power EZ Charge Locator / Public NCR Directory'),
    confidence_level = IF(latitude IS NOT NULL AND longitude IS NOT NULL, 'HIGH', 'LOW'),
    retrieved_at = COALESCE(retrieved_at, NOW())
WHERE station_slug IS NULL OR station_slug = '';

-- 4. Update Official App Links & Social Handles
UPDATE NetworkOperators
SET play_store_url = 'https://play.google.com/store/apps/details?id=com.tatapower.evapp',
    app_store_url = 'https://apps.apple.com/in/app/tata-power-ez-charge/id1496350476',
    network_scale_summary = '6,700+ public/semi-public/fleet charging points, 2.5 lakh+ home chargers, 1,200+ e-bus charging points, 7 lakh+ customers across 700+ cities & towns (Oct 2026 press release)',
    last_verified_at = NOW()
WHERE operator_name = 'Tata Power EZ Charge';

UPDATE SocialLinks
SET url = 'https://x.com/tatapower', handle = '@tatapower', last_verified_at = NOW()
WHERE platform = 'X_TWITTER';

UPDATE SocialLinks
SET url = 'https://www.youtube.com/@TataPowerCompanyLtd', handle = '@TataPowerCompanyLtd', last_verified_at = NOW()
WHERE platform = 'YOUTUBE';

-- 5. Seed Dr. Ambedkar International Centre (Verified Janpath Site) & Source-Backed Pending Verification Candidates
INSERT INTO Stations (
    station_name, station_slug, address, locality, city, state, postal_code, country,
    latitude, longitude, maps_url, operator_name, connector_types, charger_capacity_kw,
    charger_type, gun_count, opening_time, closing_time, station_status,
    verification_status, approval_status, source_url, source_type, source_name,
    published_at, retrieved_at, last_verified_at, confidence_level, record_origin, is_demo
) VALUES
(
    'Tata Power EZ Charge - Dr Ambedkar International Centre',
    'dr-ambedkar-international-centre-janpath',
    '15, Janpath Road, Windsor Place, New Delhi',
    'Janpath', 'New Delhi', 'Delhi', '110001', 'India',
    28.6200000, 77.2100000,
    'https://www.google.com/maps/search/?api=1&query=15+Janpath+New+Delhi+110001',
    'Tata Power EZ Charge', 'CCS2, TYPE2', '60 kW DC / 22 kW AC', 'DC Fast & AC Type-2', 2,
    '06:00:00', '23:00:00', 'ACTIVE',
    'VERIFIED', 'APPROVED',
    'https://www.tatapower.com/ezcharge', 'COMPANY_ANNOUNCEMENT',
    'Tata Power / Dr. Ambedkar Foundation April 2023 Installation',
    '2023-04-01', NOW(), NOW(), 'HIGH', 'OFFICIAL_COMPANY_SOURCE', 0
)
ON DUPLICATE KEY UPDATE
    verification_status = VALUES(verification_status),
    source_name = VALUES(source_name),
    last_verified_at = NOW();

INSERT INTO Stations (
    station_name, station_slug, address, locality, city, state, postal_code, country,
    latitude, longitude, operator_name, connector_types, charger_capacity_kw,
    charger_type, gun_count, opening_time, closing_time, station_status,
    verification_status, approval_status, source_url, source_type, source_name,
    published_at, retrieved_at, last_verified_at, confidence_level, record_origin, is_demo
) VALUES
('Tata Power EZ Charge - Pacific Mall Dwarka', 'pacific-mall-dwarka-delhi', 'Pacific Mall, Sector 21 Dwarka, New Delhi (exact bay coordinates pending verification)', 'Dwarka', 'New Delhi', 'Delhi', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2, TYPE2', 'Pending site verification', 'Public Mall Charger', NULL, '06:00:00', '23:00:00', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/ezcharge', 'SOCIAL_ANNOUNCEMENT', 'Tata Power Corporate Social Reference', NULL, NOW(), NOW(), 'LOW', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Sunrise Hyundai Patparganj', 'sunrise-hyundai-patparganj-delhi', 'Sunrise Hyundai, Patparganj Industrial Area, Delhi (exact GPS verification pending)', 'Patparganj', 'New Delhi', 'Delhi', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2, TYPE2', 'Pending site verification', 'Dealership Public Charger', NULL, '08:00:00', '20:00:00', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/ezcharge', 'SOCIAL_ANNOUNCEMENT', 'Tata Power Corporate Social Reference', NULL, NOW(), NOW(), 'LOW', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Yamuna Expressway LHS 35 KM', 'yamuna-expressway-lhs-35-km', 'Yamuna Expressway LHS 35 KM (exact highway coordinates pending Places verification)', 'Yamuna Expressway 35 KM', 'Greater Noida', 'Uttar Pradesh', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '120 kW + 60 kW', 'Highway DC Fast Hub', 4, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power September 2026 Press Release', '2026-09-01', NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Yamuna Expressway LHS 107 KM', 'yamuna-expressway-lhs-107-km', 'Yamuna Expressway LHS 107 KM (exact highway coordinates pending Places verification)', 'Yamuna Expressway 107 KM', 'Mathura', 'Uttar Pradesh', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '120 kW + 120 kW + 60 kW', 'Highway DC Fast Hub', 6, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power September 2026 Press Release', '2026-09-01', NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Yamuna Expressway RHS 100 KM', 'yamuna-expressway-rhs-100-km', 'Yamuna Expressway RHS 100 KM (exact highway coordinates pending Places verification)', 'Yamuna Expressway 100 KM', 'Mathura', 'Uttar Pradesh', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '120 kW + 120 kW', 'Highway DC Fast Hub', 4, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power September 2026 Press Release', '2026-09-01', NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Yamuna Expressway RHS 16 KM', 'yamuna-expressway-rhs-16-km', 'Yamuna Expressway RHS 16 KM (exact highway coordinates pending Places verification)', 'Yamuna Expressway 16 KM', 'Greater Noida', 'Uttar Pradesh', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '120 kW + 60 kW', 'Highway DC Fast Hub', 4, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power September 2026 Press Release', '2026-09-01', NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Eternity Kanpur IHCL SeleQtions', 'eternity-kanpur-ihcl-seleqtions', 'Eternity, IHCL SeleQtions, Kanpur (exact GPS verification pending)', 'Kanpur', 'Kanpur', 'Uttar Pradesh', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '60 kW', 'Hospitality DC Fast', NULL, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power Corporate Release', NULL, NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Deepu Chauhan Food Court NH 19', 'deepu-chauhan-food-court-nh19-kanpur', 'Deepu Chauhan Food Court, NH 19, Kanpur (exact GPS verification pending)', 'NH 19 Corridor', 'Kanpur', 'Uttar Pradesh', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '2 x 60 kW', 'Highway DC Fast', NULL, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power Corporate Release', NULL, NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - 7 Midway Plaza Suryapet', '7-midway-plaza-suryapet', '7 Midway Plaza, Suryapet (exact GPS verification pending)', 'NH 65 Corridor', 'Suryapet', 'Telangana', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '240 kW', 'Ultra-Fast Plaza Hub', NULL, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power Corporate Release', NULL, NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - Hotel Vivera Narketpalle', 'hotel-vivera-narketpalle', 'Hotel Vivera, Narketpalle (exact GPS verification pending)', 'Narketpalle', 'Narketpalle', 'Telangana', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '2 x 120 kW', 'Highway Ultra-Fast', NULL, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power Corporate Release', NULL, NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - ILabs Hyderabad', 'ilabs-hyderabad', 'ILabs Technology Centre, Hyderabad (exact GPS verification pending)', 'Madhapur', 'Hyderabad', 'Telangana', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '360 kW', 'Ultra-Fast Tech Hub', NULL, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power Corporate Release', NULL, NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0),
('Tata Power EZ Charge - The Leela Mega Charger Hub Mumbai', 'the-leela-mega-charger-hub-mumbai', 'The Leela Mumbai Airport Precinct, Mumbai (exact bay coordinates pending verification)', 'Andheri East', 'Mumbai', 'Maharashtra', NULL, 'India', NULL, NULL, 'Tata Power EZ Charge', 'CCS2', '600 kW (6x60 kW + 2x120 kW)', 'Mega Charger Hub', 16, '00:00:00', '23:59:59', 'ACTIVE', 'PENDING_VERIFICATION', 'APPROVED', 'https://www.tatapower.com/news-and-media/media-releases', 'PRESS_RELEASE', 'Tata Power & TATA.ev Mumbai Mega Hub Release', NULL, NOW(), NOW(), 'MEDIUM', 'OFFICIAL_COMPANY_SOURCE', 0)
ON DUPLICATE KEY UPDATE
    charger_capacity_kw = VALUES(charger_capacity_kw),
    gun_count = VALUES(gun_count),
    last_verified_at = NOW();

-- 6. Ensure every station has an initial opaque Station Identification QR token
INSERT INTO StationQRCodes (station_id, qr_token, qr_status, scan_count)
SELECT s.station_id, LOWER(REPLACE(UUID(), '-', '')), 'ACTIVE', 0
FROM Stations s
LEFT JOIN StationQRCodes q ON q.station_id = s.station_id AND q.qr_status = 'ACTIVE'
WHERE q.qr_id IS NULL;

-- 7. Seed Synthetic Example-Domain Customer & Enrich DataSources Register
INSERT INTO Users (full_name, email, phone, password_hash, role, account_status, is_demo)
VALUES (
    'Demo EV Customer 01',
    'demo.customer01@example.test',
    '+91-9000000001',
    'scrypt:32768:8:1$DemoSalt2026$4f2b82a4e8c9d0b1a23f9910e4c8f11e5d3a7f2b90c64112e58e0f87c3a1a229',
    'OWNER',
    'ACTIVE',
    1
)
ON DUPLICATE KEY UPDATE is_demo = 1;

INSERT INTO DataSources (
    data_item, category, source_name, source_type, source_url, published_at, retrieved_at,
    verification_date, data_status, confidence_level, record_origin, associated_record_count, notes
) VALUES
('Tata Power Oct 2026 Press Release Scale (6,700+ points, 2.5L+ home, 1,200+ e-bus, 7L+ customers, 700+ cities)', 'Network Statistics', 'Tata Power Official Media Release', 'PRESS_RELEASE', 'https://www.tatapower.com/news-and-media/media-releases', '2026-10-12', NOW(), '2026-11-12', 'VERIFIED', 'HIGH', 'OFFICIAL_COMPANY_SOURCE', 5, 'Primary Oct 2026 national network counters. Historical portal pages showing 5,500+/620+ reflect earlier publication dates & scopes.'),
('Tata Power EZ Charge Official Mobile App Listings (Android & iOS)', 'App Ecosystem', 'Google Play Store & Apple App Store', 'APP_STORE_LISTING', 'https://play.google.com/store/apps/details?id=com.tatapower.evapp', '2026-10-12', NOW(), '2026-11-12', 'VERIFIED', 'HIGH', 'OFFICIAL_COMPANY_SOURCE', 2, 'Verified official consumer app listings: Android com.tatapower.evapp and iOS id1496350476.'),
('Tata Power Official Station Locator & NCR Candidate Verification Set', 'Station Directory', 'Tata Power EZ Charge Locator & Press Releases', 'OFFICIAL_LOCATOR', 'https://www.tatapower.com/ezcharge', '2026-10-12', NOW(), '2026-11-12', 'VERIFIED', 'HIGH', 'OFFICIAL_COMPANY_SOURCE', 27, '15 coordinate-verified stations mapped; 12 press/social candidate locations flagged PENDING_VERIFICATION until GPS verified.'),
('Synthetic Demo Accounts (@example.test), Bookings & Metered Sessions', 'Portal Simulation', 'EZ Charge Network Portal Sandbox Generator', 'SYSTEM_SEED', NULL, NULL, NOW(), '2026-11-12', 'DEMO', 'HIGH', 'DEMONSTRATION_SEED', 10, 'Synthetic demonstration users, vehicle records, reservations, and kWh sessions isolated from official Tata Power telemetry.')
ON DUPLICATE KEY UPDATE
    category = VALUES(category),
    source_type = VALUES(source_type),
    published_at = COALESCE(VALUES(published_at), published_at),
    retrieved_at = NOW(),
    confidence_level = VALUES(confidence_level),
    record_origin = VALUES(record_origin),
    associated_record_count = VALUES(associated_record_count),
    notes = VALUES(notes);

