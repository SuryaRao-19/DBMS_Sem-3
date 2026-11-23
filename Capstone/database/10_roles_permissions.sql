-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - PHASE 4: SECURITY & ACCESS CONTROL
-- Database: MySQL 8.0+
-- File: database/06_roles_permissions.sql
-- ============================================================

USE ev_charging_db;

-- ------------------------------------------------------------
-- Create Database Roles
-- ------------------------------------------------------------
DROP ROLE IF EXISTS 'station_admin_role', 'ev_owner_role', 'app_backend_role';

CREATE ROLE 'station_admin_role';
CREATE ROLE 'ev_owner_role';
CREATE ROLE 'app_backend_role';

-- ------------------------------------------------------------
-- Grant Privileges to Roles
-- ------------------------------------------------------------

-- Role 1: Station Administrator / Operator
-- Full operational permissions across stations, points, tariffs, and reporting
GRANT SELECT, INSERT, UPDATE, DELETE ON ev_charging_db.* TO 'station_admin_role';
GRANT EXECUTE ON PROCEDURE ev_charging_db.CompleteChargingSession TO 'station_admin_role';
GRANT EXECUTE ON FUNCTION ev_charging_db.CalculateChargingCost TO 'station_admin_role';

-- Role 2: EV Owner
-- Read-only on stations and points; write access only on bookings, vehicles, and sessions
GRANT SELECT ON ev_charging_db.Stations TO 'ev_owner_role';
GRANT SELECT ON ev_charging_db.ChargingPoints TO 'ev_owner_role';
GRANT SELECT, INSERT, UPDATE, DELETE ON ev_charging_db.Vehicles TO 'ev_owner_role';
GRANT SELECT, INSERT, UPDATE ON ev_charging_db.Bookings TO 'ev_owner_role';
GRANT SELECT, INSERT, UPDATE ON ev_charging_db.ChargingSessions TO 'ev_owner_role';
GRANT SELECT, INSERT ON ev_charging_db.Payments TO 'ev_owner_role';
GRANT EXECUTE ON FUNCTION ev_charging_db.CalculateChargingCost TO 'ev_owner_role';

-- Role 3: Web Application Backend Connection
-- Controlled privileges for the web application data tier
GRANT SELECT, INSERT, UPDATE, DELETE ON ev_charging_db.* TO 'app_backend_role';
GRANT EXECUTE ON PROCEDURE ev_charging_db.CompleteChargingSession TO 'app_backend_role';
GRANT EXECUTE ON FUNCTION ev_charging_db.CalculateChargingCost TO 'app_backend_role';

-- ------------------------------------------------------------
-- Optional: Example Application Service User Creation
-- ------------------------------------------------------------
-- CREATE USER IF NOT EXISTS 'ev_app_user'@'localhost' IDENTIFIED BY 'SecureEvPass!2026';
-- GRANT 'app_backend_role' TO 'ev_app_user'@'localhost';
-- SET DEFAULT ROLE 'app_backend_role' TO 'ev_app_user'@'localhost';
-- FLUSH PRIVILEGES;
