"""
Security, Access Control, and Transaction Rollback Tests
EV Charging Station Management System - DBMS Capstone Project
"""
import pytest
from app.db import transaction, query_one, execute
from app.services.vehicle_service import delete_vehicle
from app.services.booking_service import cancel_booking


def test_unauthorized_redirect_for_anonymous_user(client):
    """Verify that anonymous requests to protected routes redirect to login."""
    res = client.get("/admin/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.location

    res2 = client.get("/owner/dashboard", follow_redirects=False)
    assert res2.status_code == 302
    assert "/login" in res2.location


def test_ev_owner_blocked_from_admin_portal(owner_client):
    """Verify that an EV owner cannot access admin routes (HTTP 403 Forbidden)."""
    res = owner_client.get("/admin/dashboard")
    assert res.status_code == 403

    res_stations = owner_client.get("/admin/stations")
    assert res_stations.status_code == 403

    res_reports = owner_client.get("/admin/reports")
    assert res_reports.status_code == 403


def test_admin_blocked_from_owner_portal(admin_client):
    """Verify that an Admin account cannot access EV Owner routes."""
    res = admin_client.get("/owner/dashboard")
    assert res.status_code == 403


def test_idor_protection_cannot_delete_other_user_vehicle():
    """
    Verify Insecure Direct Object Reference (IDOR) protection:
    Owner 2 (Aarav) cannot delete Vehicle 2 (belonging to Owner 3 Priya).
    """
    success, err = delete_vehicle(vehicle_id=2, user_id=2)
    assert success is False
    assert "not found or you do not have permission" in err

    # Confirm vehicle 2 still exists in DB
    v = query_one("SELECT vehicle_id FROM Vehicles WHERE vehicle_id = 2")
    assert v is not None


def test_idor_protection_cannot_cancel_other_user_booking():
    """
    Verify that an EV owner cannot cancel a reservation belonging to another user.
    Booking #2 belongs to User 3 (Priya); User 2 (Aarav) attempts to cancel it.
    """
    success, err = cancel_booking(booking_id=2, user_id=2)
    assert success is False
    assert "Booking not found or permission denied" in err


def test_atomic_transaction_rollback_on_intentional_failure():
    """
    Verify that multi-step database operations roll back completely
    if an error occurs in the middle of a transaction.
    """
    initial_tariff = query_one("SELECT tariff_per_kwh FROM ChargingPoints WHERE point_id = 1")["tariff_per_kwh"]

    rolled_back = False
    try:
        with transaction() as cur:
            # Step 1: Valid update
            cur.execute("UPDATE ChargingPoints SET tariff_per_kwh = 99.99 WHERE point_id = 1")
            
            # Step 2: Intentional failure violating CHECK constraint (battery_capacity_kwh > 0)
            cur.execute("INSERT INTO Vehicles (user_id, registration_no, make, model, battery_capacity_kwh) "
                        "VALUES (2, 'FAIL_REG_01', 'Test', 'Test', -50.00)")
    except Exception:
        rolled_back = True

    assert rolled_back is True

    # Verify that Step 1 was rolled back and tariff was NOT changed
    current_tariff = query_one("SELECT tariff_per_kwh FROM ChargingPoints WHERE point_id = 1")["tariff_per_kwh"]
    assert current_tariff == initial_tariff
