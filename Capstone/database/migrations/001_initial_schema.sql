-- ============================================================
-- MIGRATION 001: Initial Core Schema (7 Tables)
-- Database: MySQL 8.0+
-- File: database/09_migrations/001_initial_schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS ev_charging_db;
USE ev_charging_db;

-- 1. Users Table
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

-- 2. Vehicles Table
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

-- 3. Stations Table
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

-- 4. ChargingPoints Table
CREATE TABLE IF NOT EXISTS ChargingPoints (
    point_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    point_code VARCHAR(30) NOT NULL,
    connector_type ENUM('TYPE2', 'CCS2', 'CHADEMO', 'GB_T') NOT NULL,
    max_power_kw DECIMAL(8,2) NOT NULL,
    tariff_per_kwh DECIMAL(10,2) NOT NULL,
    point_status ENUM('AVAILABLE', 'OCCUPIED', 'UNAVAILABLE', 'MAINTENANCE') NOT NULL DEFAULT 'AVAILABLE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (station_id, point_code),
    FOREIGN KEY (station_id) REFERENCES Stations(station_id) ON DELETE CASCADE,
    CHECK (max_power_kw > 0),
    CHECK (tariff_per_kwh >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Bookings Table
CREATE TABLE IF NOT EXISTS Bookings (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    point_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    booking_status ENUM('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED') NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id),
    FOREIGN KEY (vehicle_id) REFERENCES Vehicles(vehicle_id),
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id),
    CHECK (end_at > start_at),
    INDEX idx_booking_point_time (point_id, start_at, end_at),
    INDEX idx_booking_user_status (user_id, booking_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. ChargingSessions Table
CREATE TABLE IF NOT EXISTS ChargingSessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT UNIQUE,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    point_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME,
    energy_kwh DECIMAL(10,3) NOT NULL DEFAULT 0,
    tariff_per_kwh DECIMAL(10,2) NOT NULL,
    total_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
    session_status ENUM('IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'IN_PROGRESS',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES Bookings(booking_id),
    FOREIGN KEY (user_id) REFERENCES Users(user_id),
    FOREIGN KEY (vehicle_id) REFERENCES Vehicles(vehicle_id),
    FOREIGN KEY (point_id) REFERENCES ChargingPoints(point_id),
    CHECK (energy_kwh >= 0),
    CHECK (tariff_per_kwh >= 0),
    CHECK (total_cost >= 0),
    CHECK (end_at IS NULL OR end_at >= start_at),
    INDEX idx_session_user_date (user_id, start_at),
    INDEX idx_session_point_date (point_id, start_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Payments Table
CREATE TABLE IF NOT EXISTS Payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    transaction_reference VARCHAR(100) NOT NULL UNIQUE,
    amount DECIMAL(12,2) NOT NULL,
    payment_method ENUM('UPI', 'CARD', 'CASH', 'WALLET') NOT NULL,
    payment_status ENUM('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED') NOT NULL DEFAULT 'PENDING',
    paid_at DATETIME,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES ChargingSessions(session_id),
    CHECK (amount >= 0),
    INDEX idx_payment_status_date (payment_status, paid_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
