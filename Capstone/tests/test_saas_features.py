"""
SaaS Platform, Discovery, Admin Telemetry, and Vehicle Updates Tests
EV Charging Station Management System - DBMS Capstone Project
"""
import pytest
from app.db import execute, query_one
from app.services.vehicle_service import update_vehicle, add_vehicle
from app.services.auth_service import update_user_profile, authenticate_user


def test_public_landing_page(client):
    """Verify that public landing page loads with real DB metric counters."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "EV ChargeNet" in html
    assert "Active Stations" in html
    assert "Charging Points" in html
    assert "Find Charging Stations" in html


def test_public_stations_directory(client):
    """Verify that station discovery supports city, connector, and query filtering."""
    # All stations
    res = client.get("/stations")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Find EV Charging Stations" in html

    # Filter by city
    res_city = client.get("/stations?city=Bangalore")
    assert res_city.status_code == 200

    # Search by text
    res_search = client.get("/stations?q=Eco")
    assert res_search.status_code == 200


def test_station_detail_page(client):
    """Verify that station detail page lists all dispensers, live status, and tariffs."""
    res = client.get("/stations/1")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Connaught Place EV Hub" in html
    assert "Available Charging Dispensers" in html
    assert "CP-01" in html
    assert "CCS2" in html




def test_station_detail_nonexistent(client):
    """Verify that requesting a nonexistent station redirects safely with flash message."""
    res = client.get("/stations/9999", follow_redirects=True)
    assert res.status_code == 200
    assert "Charging station not found." in res.data.decode("utf-8")


def test_admin_users_management(admin_client):
    """Verify that admin can inspect all registered users and their activity metrics."""
    res = admin_client.get("/admin/users")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "User &amp; Account Management" in html or "User & Account Management" in html
    assert "admin@evdemo.com" in html
    assert "aarav@example.com" in html


def test_admin_user_status_toggle(admin_client):
    """Verify that admin can toggle a user's account status, while self-deactivation is blocked."""
    # Self-deactivation prevention for Admin #1
    res_self = admin_client.post("/admin/users/1/toggle-status", follow_redirects=True)
    assert res_self.status_code == 200
    assert "cannot deactivate your own active administrator account" in res_self.data.decode("utf-8")

    # Toggle status of test user #4 (Kavita)
    user_before = query_one("SELECT account_status FROM Users WHERE user_id = 4")
    orig_status = user_before["account_status"]

    res_toggle = admin_client.post("/admin/users/4/toggle-status", follow_redirects=True)
    assert res_toggle.status_code == 200

    user_after = query_one("SELECT account_status FROM Users WHERE user_id = 4")
    expected_status = "INACTIVE" if orig_status == "ACTIVE" else "ACTIVE"
    assert user_after["account_status"] == expected_status

    # Revert back to original
    execute("UPDATE Users SET account_status = %s WHERE user_id = 4", (orig_status,))


def test_admin_system_health_diagnostics(admin_client):
    """Verify that admin system health displays live DBMS diagnostics."""
    res = admin_client.get("/admin/system-health")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Database &amp; System Health Diagnostics" in html or "Database & System Health Diagnostics" in html
    assert "MySQL" in html
    assert "ev_charging_db" in html
    assert "3NF Schema Entities" in html
    assert "Stored Routines" in html
    assert "CalculateChargingCost" in html
    assert "CompleteChargingSession" in html


def test_owner_vehicle_edit():
    """Verify that vehicle edit updates make, model, registration, and capacity."""
    # User 2 owns Vehicle 1 (DL01EV1234)
    v_orig = query_one("SELECT * FROM Vehicles WHERE vehicle_id = 1")

    success, err = update_vehicle(
        vehicle_id=1,
        user_id=2,
        registration_no="DL01EV1234",
        make="Tata Motors",
        model="Nexon EV Max",
        battery_capacity_kwh=40.5
    )
    assert success is True
    assert err is None

    v_updated = query_one("SELECT * FROM Vehicles WHERE vehicle_id = 1")
    assert v_updated["make"] == "Tata Motors"
    assert v_updated["model"] == "Nexon EV Max"
    assert float(v_updated["battery_capacity_kwh"]) == 40.5

    # Revert to original
    execute(
        "UPDATE Vehicles SET make = %s, model = %s, battery_capacity_kwh = %s WHERE vehicle_id = 1",
        (v_orig["make"], v_orig["model"], v_orig["battery_capacity_kwh"])
    )


def test_owner_vehicle_edit_idor_protection():
    """Verify that User 3 cannot edit Vehicle 1 belonging to User 2."""
    success, err = update_vehicle(
        vehicle_id=1,
        user_id=3,
        registration_no="DL01EV1234",
        make="Hacked Make",
        model="Hacked Model",
        battery_capacity_kwh=50.0
    )
    assert success is False
    assert "permission" in err or "not found" in err


def test_owner_session_receipt(owner_client):
    """Verify that EV owner can view an itemized invoice receipt for their session."""
    # Session 1 belongs to User 2 (Aarav)
    res = owner_client.get("/owner/session/1")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Official Charging Session Receipt" in html
    assert "INVOICE #" in html
    assert "Aarav Sharma" in html
    assert "Connaught Place EV Hub" in html
    assert "Print / Save Receipt" in html



def test_owner_session_receipt_idor(other_owner_client):
    """Verify that an EV owner cannot access another user's invoice receipt."""
    # Session 1 belongs to User 2 (Aarav). User 3 (Priya) tries to access it.
    res = other_owner_client.get("/owner/session/1", follow_redirects=True)
    assert res.status_code == 200
    assert "access denied" in res.data.decode("utf-8").lower()


def test_user_profile_update_and_password_change(owner_client):
    """Verify that user can update profile details and change password with verification."""
    # 1. Update name and phone
    res_update = owner_client.post("/profile", data={
        "full_name": "Aarav Sharma (Updated)",
        "phone": "+91 98888 77777",
        "current_password": "",
        "new_password": "",
        "confirm_new_password": ""
    }, follow_redirects=True)
    assert res_update.status_code == 200
    assert "Profile updated successfully" in res_update.data.decode("utf-8")

    u = query_one("SELECT full_name, phone FROM Users WHERE user_id = 2")
    assert u["full_name"] == "Aarav Sharma (Updated)"
    assert u["phone"] == "+91 98888 77777"

    # 2. Test password change with WRONG current password
    res_wrong_pw = owner_client.post("/profile", data={
        "full_name": "Aarav Sharma",
        "phone": "+91 98888 77777",
        "current_password": "WrongPassword999",
        "new_password": "NewSecret@2026",
        "confirm_new_password": "NewSecret@2026"
    }, follow_redirects=True)
    assert res_wrong_pw.status_code == 200
    assert "Incorrect current password" in res_wrong_pw.data.decode("utf-8")

    # 3. Test password change with CORRECT current password
    res_correct_pw = owner_client.post("/profile", data={
        "full_name": "Aarav Sharma",
        "phone": "+91 98765 43210",
        "current_password": "Owner@123",
        "new_password": "NewOwnerPass@123",
        "confirm_new_password": "NewOwnerPass@123"
    }, follow_redirects=True)
    assert res_correct_pw.status_code == 200
    assert "Profile updated successfully" in res_correct_pw.data.decode("utf-8")

    # Confirm authentication with new password
    auth_user, auth_err = authenticate_user("aarav@example.com", "NewOwnerPass@123")
    assert auth_err is None
    assert auth_user["user_id"] == 2

    # Revert password back to Owner@123
    update_user_profile(user_id=2, full_name="Aarav Sharma", phone="+91 98765 43210", current_password="NewOwnerPass@123", new_password="Owner@123")


def test_admin_reports_csv_export(admin_client):
    """Verify that admin can export reports as CSV files with correct MIME type and headers."""
    # 1. Revenue CSV export
    res_rev = admin_client.get("/admin/reports/export?type=revenue")
    assert res_rev.status_code == 200
    assert "text/csv" in res_rev.content_type
    assert "attachment; filename=ev_monthly_revenue_" in res_rev.headers.get("Content-Disposition", "")
    csv_text = res_rev.data.decode("utf-8")
    assert "Station ID,Station Name,City,Billing Month" in csv_text

    # 2. Energy CSV export
    res_eng = admin_client.get("/admin/reports/export?type=energy")
    assert res_eng.status_code == 200
    assert "text/csv" in res_eng.content_type
    assert "attachment; filename=ev_monthly_energy_" in res_eng.headers.get("Content-Disposition", "")
    assert "Completed Sessions,Total Energy (kWh)" in res_eng.data.decode("utf-8")

    # 3. Utilization CSV export
    res_util = admin_client.get("/admin/reports/export?type=utilization")
    assert res_util.status_code == 200
    assert "text/csv" in res_util.content_type
    assert "attachment; filename=ev_station_utilization_" in res_util.headers.get("Content-Disposition", "")
    assert "Dispenser Count,Total Sessions,Total Charge Hours" in res_util.data.decode("utf-8")

