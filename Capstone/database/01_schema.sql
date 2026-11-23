-- ============================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DBMS CAPSTONE PROJECT - TOOLKIT FILE 1: DATABASE SCHEMA
-- Database: MySQL 8.0+ (InnoDB)
-- File: database/01_schema.sql
-- Description: Creates database and 9 normalized relational tables
-- Safety Rule: NO DROP DATABASE statements. Repeatable via IF NOT EXISTS.
-- ============================================================

CREATE DATABASE IF NOT EXISTS ev_charging_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ev_charging_db;

-- ------------------------------------------------------------
-- 1. USERS TABLE
-- Stores user credentials, contact information, role, and account status
-- Role: 'ADMIN' for operators/evaluators, 'OWNER' for EV drivers
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('ADMIN', 'OWNER') NOT NULL DEFAULT 'OWNER',
    account_status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2. VEHICLES TABLE
-- Electric vehicles owned by registered drivers (1:N from Users)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Vehicles (
    vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    registration_no VARCHAR(30) NOT NULL UNIQUE,
    make VARCHAR(60) NOT NULL,
    model VARCHAR(60) NOT NULL,
    battery_capacity_kwh DECIMAL(8,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CHECK (battery_capacity_kwh > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 3. CHARGING STATIONS TABLE
-- Physical charging hub locations with operating hours and city
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Stations (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    station_name VARCHAR(120) NOT NULL,
    address VARCHAR(255) NOT NULL,
    city VARCHAR(80) NOT NULL,
    opening_time TIME,
    closing_time TIME,
    station_status ENUM('ACTIVE', 'INACTIVE', 'MAINTENANCE') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 4. CHARGING POINTS TABLE
-- Individual charging dispensers located at a charging station
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ChargingPoints (
    point_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    point_code VARCHAR(30) NOT NULL,
    connector_type ENUM('TYPE2', 'CCS2', 'CHADEMO', 'GB_T') NOT NULL,
    max_power_kw DECIMAL(8,2) NOT NULL,
    tariff_per_kwh DECIMAL(10,2) NOT NULL,
    point_status ENUM('AVAILABLE', 'OCCUPIED', 'UNAVAILABLE', 'MAINTENANCE') NOT NULL DEFAULT 'AVAILABLE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_station_point (station_id, point_code),
    FOREIGN KEY (station_id) REFERENCES Stations(station_id) ON DELETE CASCADE,
    CHECK (max_power_kw > 0),
    CHECK (tariff_per_kwh >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 5. BOOKINGS TABLE
-- Time-slot reservations made by drivers for specific charging points
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Bookings (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    point_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    booking_status ENUM('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED') NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (vehicle_id) REFERENCES Vehicles(vehicle_id) ON DELETE RESTRICT,
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id) ON DELETE RESTRICT,
    CHECK (end_at > start_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 6. CHARGING SESSIONS TABLE
-- Real-time and completed energy dispensation records
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ChargingSessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT UNIQUE,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    point_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME,
    energy_kwh DECIMAL(10,3) NOT NULL DEFAULT 0.000,
    tariff_per_kwh DECIMAL(10,2) NOT NULL,
    total_cost DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    session_status ENUM('IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'IN_PROGRESS',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES Bookings(booking_id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (vehicle_id) REFERENCES Vehicles(vehicle_id) ON DELETE RESTRICT,
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id) ON DELETE RESTRICT,
    CHECK (energy_kwh >= 0),
    CHECK (tariff_per_kwh >= 0),
    CHECK (total_cost >= 0),
    CHECK (end_at IS NULL OR end_at >= start_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 7. PAYMENTS TABLE
-- Financial billing records linked to charging sessions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    transaction_reference VARCHAR(100) NOT NULL UNIQUE,
    amount DECIMAL(12,2) NOT NULL,
    payment_method ENUM('UPI', 'CARD', 'CASH', 'WALLET') NOT NULL,
    payment_status ENUM('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED') NOT NULL DEFAULT 'PENDING',
    paid_at DATETIME,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES ChargingSessions(session_id) ON DELETE RESTRICT,
    CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 8. AUDIT LOGS TABLE
-- Audit trail tracking administrative operations and privilege events
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS AuditLogs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(80) NOT NULL,
    entity_name VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    details TEXT,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 9. SYSTEM SETTINGS TABLE
-- Centralized key-value operational configuration parameters
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS SystemSettings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    description VARCHAR(255) NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 10. CONTACT MESSAGES TABLE
-- Stores customer/partner enquiries and Web3Forms delivery status
-- ------------------------------------------------------------
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
