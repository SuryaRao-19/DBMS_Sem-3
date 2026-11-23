-- ====================================================================
-- EV CHARGING STATION MANAGEMENT SYSTEM
-- DESTRUCTIVE DATABASE RESET SCRIPT (DEVELOPMENT ENVIRONMENT ONLY)
-- File: database/reset_database_DEV_ONLY.sql
-- ====================================================================
--
-- !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
-- WARNING: THIS SCRIPT COMPLETELY DROPS THE DATABASE AND ALL DATA!
-- DO NOT RUN IN PRODUCTION OR ON ANY DATABASE CONTAINING VALUABLE DATA.
-- ALL USERS, VEHICLES, BOOKINGS, SESSIONS, PAYMENTS, AND LOGS WILL BE LOST.
-- !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

SELECT 'WARNING: Executing destructive reset of ev_charging_db...' AS warning_notice;

DROP DATABASE IF EXISTS ev_charging_db;
CREATE DATABASE ev_charging_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ev_charging_db;

SELECT 'Database ev_charging_db dropped and recreated cleanly.' AS reset_status;
