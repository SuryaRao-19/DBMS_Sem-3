"""
Database Migration: Data Provenance & Support Enhancements
Adds fields for Phase 3 and Phase 8 (Cash Payments), updates enums safely.
"""
from app.db import execute, query_all

def run_migration():
    # 1. Stations table enhancements
    cols = [c['Field'] for c in query_all('DESCRIBE Stations')]
    print('Current cols in Stations:', len(cols))

    if 'external_provider' not in cols:
        execute('ALTER TABLE Stations ADD COLUMN external_provider VARCHAR(80) NULL')
        print('Added external_provider to Stations')

    if 'external_station_id' not in cols:
        execute('ALTER TABLE Stations ADD COLUMN external_station_id VARCHAR(120) NULL')
        print('Added external_station_id to Stations')

    if 'connector_details' not in cols:
        execute('ALTER TABLE Stations ADD COLUMN connector_details VARCHAR(255) NULL')
        print('Added connector_details to Stations')

    if 'data_license' not in cols:
        execute('ALTER TABLE Stations ADD COLUMN data_license VARCHAR(255) NULL')
        print('Added data_license to Stations')

    execute("""
        ALTER TABLE Stations MODIFY COLUMN verification_status 
        ENUM('VERIFIED','OPERATOR_REPORTED','IMPORTED','PENDING_VERIFICATION','PENDING_REVIEW','UNVERIFIED','HISTORICAL','DEMO','ESTIMATED','UNAVAILABLE','OUTDATED') 
        NOT NULL DEFAULT 'PENDING_VERIFICATION'
    """)
    print('Updated verification_status ENUM')

    execute("""
        UPDATE Stations 
        SET external_provider = COALESCE(external_provider, source_name, 'TATA_POWER_EZ_CHARGE'),
            external_station_id = COALESCE(external_station_id, external_source_id, CONCAT('STN-', station_id)),
            connector_details = COALESCE(connector_details, connector_types),
            data_license = COALESCE(data_license, license_info, 'Public Domain / Fair Use')
    """)
    print('Stations backfill complete')

    # 2. Payments table enhancements for Cash & Phase 7/8
    p_cols = [c['Field'] for c in query_all('DESCRIBE Payments')]
    if 'cash_collected_by' not in p_cols:
        execute('ALTER TABLE Payments ADD COLUMN cash_collected_by INT NULL')
        print('Added cash_collected_by to Payments')
    if 'cash_collected_at' not in p_cols:
        execute('ALTER TABLE Payments ADD COLUMN cash_collected_at DATETIME NULL')
        print('Added cash_collected_at to Payments')
    if 'cash_notes' not in p_cols:
        execute('ALTER TABLE Payments ADD COLUMN cash_notes VARCHAR(255) NULL')
        print('Added cash_notes to Payments')

    # Update payment_status enum to include PAYMENT_DUE
    execute("""
        ALTER TABLE Payments MODIFY COLUMN payment_status 
        ENUM('CREATED','PENDING','AUTHORIZED','CAPTURED','SUCCESS','FAILED','EXPIRED','REFUNDED','PAYMENT_DUE') 
        NOT NULL DEFAULT 'PENDING'
    """)
    print('Updated Payments payment_status ENUM with PAYMENT_DUE')

    # Update Bookings booking_status enum to include PENDING_PAYMENT, EXPIRED
    execute("""
        ALTER TABLE Bookings MODIFY COLUMN booking_status 
        ENUM('PENDING','PENDING_PAYMENT','CONFIRMED','CANCELLED','COMPLETED','EXPIRED') 
        NOT NULL DEFAULT 'CONFIRMED'
    """)
    print('Updated Bookings booking_status ENUM')

    print('ALL MIGRATIONS COMPLETED SUCCESSFULLY!')

if __name__ == '__main__':
    run_migration()
