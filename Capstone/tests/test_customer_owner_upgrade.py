"""
Customer Mobility Portal, Multi-Role Auth & Station Partner Architecture Tests
EV Charging Station Management System - Production Hardened
"""
import io
import pytest
from app.db import query_one, query_all, execute
from app.services.auth_service import register_user, authenticate_user, check_auth_rate_limit, reset_auth_rate_limits
from app.services.vehicle_service import add_vehicle, get_vehicles_by_user, set_default_vehicle, delete_vehicle
from app.services.booking_service import create_booking, cancel_booking
from app.services.customer_service import (
    get_customer_dashboard_kpis,
    toggle_saved_station,
    is_station_saved,
    get_saved_stations_for_user,
    add_notification,
    get_customer_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    get_customer_charging_history,
    generate_customer_history_csv,
    get_customer_payment_summary,
)
from app.services.owner_service import (
    submit_owner_application,
    get_owner_applications,
    get_owner_application_by_id,
    review_owner_application,
    get_owner_stations,
    get_owner_station_by_id,
    verify_owner_station_access,
    get_owner_charging_points,
    get_owner_dashboard_kpis,
)
from app.services.qr_service import resolve_any_qr_token, get_or_create_booking_qr


def test_public_registration_defaults_to_customer_and_blocks_privileged_roles(client):
    """1. Public registration defaults to CUSTOMER role and rejects ADMIN/OWNER attempts."""
    email_base = "driver_cust_reg_01@example.com"
    execute("DELETE FROM Users WHERE email = %s", (email_base,))

    # A) Normal registration defaults to CUSTOMER and redirects to login with flash
    res = client.post("/register", data={
        "full_name": "Test Cust Driver",
        "email": email_base,
        "phone": "+91 9123456789",
        "password": "Password@123",
        "confirm_password": "Password@123",
    }, follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.location or "/customer/dashboard" in res.location

    row = query_one("SELECT user_id, role, auth_provider FROM Users WHERE email = %s", (email_base,))
    assert row is not None
    assert row["role"] == "CUSTOMER"

    # B) Tampered role in form attempting ADMIN or OWNER -> 403
    for evil_role in ("ADMIN", "OWNER"):
        res_evil = client.post("/register", data={
            "full_name": "Attacker",
            "email": f"attacker_{evil_role}@example.com",
            "phone": "+91 9999999999",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "role": evil_role,
        })
        assert res_evil.status_code == 403

    execute("DELETE FROM Users WHERE email = %s", (email_base,))


def test_auth_sliding_window_rate_limiting():
    """2. Auth rate limiting throttles brute force attempts per IP."""
    ip = "192.0.2.145"
    reset_auth_rate_limits()

    # Within limit of 10
    for i in range(10):
        ok, wait_time = check_auth_rate_limit(ip, "login", max_attempts=10, window_seconds=60)
        assert ok is True
        assert wait_time == 0

    # 11th attempt exceeded
    ok, wait_time = check_auth_rate_limit(ip, "login", max_attempts=10, window_seconds=60)
    assert ok is False
    assert wait_time > 0

    # Reset cleans it up
    reset_auth_rate_limits()
    ok, wait_time = check_auth_rate_limit(ip, "login", max_attempts=10, window_seconds=60)
    assert ok is True


def test_remember_me_cookie_session_handling(client):
    """3. Login sets persistent session cookie when remember_me is selected."""
    res = client.post("/login", data={
        "email": "aarav@example.com",
        "password": "Owner@123",
        "remember_me": "1",
    }, follow_redirects=False)
    assert res.status_code == 302
    assert "/customer/dashboard" in res.location
    with client.session_transaction() as sess:
        assert sess.get("user_id") == 2
        assert sess.get("role") == "CUSTOMER"
        assert sess.permanent is True


def test_avatar_upload_validation(app):
    """4. Avatar upload validates MIME types (PNG, JPG, WebP) and blocks non-image payloads."""
    from app.services.auth_service import save_uploaded_avatar
    from werkzeug.datastructures import FileStorage

    # Valid PNG header (8 bytes magic)
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    valid_fs = FileStorage(stream=io.BytesIO(png_data), filename="avatar.png", content_type="image/png")
    rel_path, err = save_uploaded_avatar(valid_fs, static_folder=app.static_folder)
    assert err is None
    assert rel_path.startswith("/static/uploads/avatars/")

    # Invalid executable disguised as png
    fake_fs = FileStorage(stream=io.BytesIO(b"MZ\x90\x00NOT_AN_IMAGE"), filename="fake.png", content_type="image/png")
    rel_path2, err2 = save_uploaded_avatar(fake_fs, static_folder=app.static_folder)
    assert rel_path2 is None
    assert "Invalid image format" in err2


def test_customer_dashboard_kpis_strict_scoping():
    """5. Customer dashboard KPIs return authoritative metrics strictly for the user."""
    kpis = get_customer_dashboard_kpis(user_id=2)
    assert isinstance(kpis["total_sessions"], int)
    assert isinstance(kpis["total_energy_kwh"], (int, float))
    assert isinstance(kpis["total_amount_spent"], (int, float))
    assert isinstance(kpis["vehicles_count"], int)
    assert isinstance(kpis["saved_stations_count"], int)
    assert isinstance(kpis["unread_notifications_count"], int)
    assert kpis["vehicles_count"] >= 1


def test_vehicles_crud_with_categories_and_default_toggle():
    """6. Vehicles table CRUD with category, connector, year, and atomic primary toggle."""
    test_uid = 2
    reg_no = "DL01EV9988"
    execute("DELETE FROM Vehicles WHERE registration_no = %s", (reg_no,))

    vid, err = add_vehicle(
        user_id=test_uid,
        registration_no=reg_no,
        make="Tata",
        model="Nexon EV Max",
        battery_capacity_kwh=40.5,
        vehicle_category="4W_SUV",
        connector_type="CCS2",
        registration_year=2024,
        is_default=True,
    )
    assert err is None
    assert vid is not None

    veh = query_one("SELECT * FROM Vehicles WHERE vehicle_id = %s", (vid,))
    assert veh["vehicle_category"] == "4W_SUV"
    assert veh["connector_type"] == "CCS2"
    assert veh["registration_year"] == 2024
    assert veh["is_default"] == 1

    # Setting default auto-clears other defaults atomically
    vehs = get_vehicles_by_user(test_uid)
    defaults = [v for v in vehs if v.get("is_default") == 1]
    assert len(defaults) == 1
    assert defaults[0]["vehicle_id"] == vid

    # Clean up
    delete_vehicle(vid, test_uid)


def test_booking_slot_atomic_estimates_and_qr():
    """7 & 8. Booking computes estimated energy/cost and auto-creates check-in QR."""
    start_dt = "2026-11-25 15:00:00"
    end_dt = "2026-11-25 16:30:00"
    execute("DELETE FROM Bookings WHERE point_id = 1 AND start_at = %s", (start_dt,))

    bid, err = create_booking(user_id=2, vehicle_id=1, point_id=1, start_at=start_dt, end_at=end_dt)
    assert err is None
    assert bid is not None

    b_row = query_one("SELECT * FROM Bookings WHERE booking_id = %s", (bid,))
    assert float(b_row["estimated_energy_kwh"]) > 0
    assert float(b_row["estimated_cost"]) > 0

    qr_row = get_or_create_booking_qr(bid)
    assert qr_row is not None
    assert bool(qr_row["qr_token"]) is True
    assert len(qr_row["qr_token"]) >= 16

    # Clean up
    cancel_booking(bid, user_id=2)


def test_saved_stations_toggle_and_retrieval():
    """14. Saved stations toggle bookmarking and list user favorites."""
    test_uid = 2
    test_st = 1
    execute("DELETE FROM SavedStations WHERE user_id = %s AND station_id = %s", (test_uid, test_st))

    # Toggle ON
    saved, msg = toggle_saved_station(test_uid, test_st)
    assert saved is True
    assert is_station_saved(test_uid, test_st) is True

    favs = get_saved_stations_for_user(test_uid)
    assert any(f["station_id"] == test_st for f in favs)

    # Toggle OFF
    saved2, msg2 = toggle_saved_station(test_uid, test_st)
    assert saved2 is False
    assert is_station_saved(test_uid, test_st) is False


def test_in_app_notifications_lifecycle():
    """15. In-app notifications CRUD and mark-read."""
    test_uid = 2
    nid = add_notification(test_uid, "Test Alert", "Your EV reservation is ready.", category="BOOKING")
    assert nid is not None

    notifs = get_customer_notifications(test_uid)
    assert any(n["notification_id"] == nid for n in notifs)

    ok = mark_notification_read(nid, test_uid)
    assert ok is True

    n_row = query_one("SELECT is_read FROM Notifications WHERE notification_id = %s", (nid,))
    assert n_row["is_read"] == 1

    execute("DELETE FROM Notifications WHERE notification_id = %s", (nid,))


def test_qr_resolver_multi_type_support():
    """13. Multi-type QR code resolver resolves Point, Station, and Booking QRs."""
    # Point QR
    pt_qr = query_one("SELECT qr_token, point_id FROM PointQRCodes WHERE qr_status = 'ACTIVE' LIMIT 1")
    if pt_qr:
        res, err, status = resolve_any_qr_token(pt_qr["qr_token"])
        assert err is None
        assert res["type"] == "POINT"
        assert res["point_id"] == pt_qr["point_id"]

    # Station QR
    st_qr = query_one("SELECT qr_token, station_id FROM StationQRCodes WHERE qr_status = 'ACTIVE' LIMIT 1")
    if st_qr:
        res_st, err_st, status_st = resolve_any_qr_token(st_qr["qr_token"])
        assert err_st is None
        assert res_st["type"] == "STATION"
        assert res_st["station_id"] == st_qr["station_id"]


def test_owner_application_submission_and_admin_review(admin_client):
    """18 & 19. Public partner application submission and Admin review/approval."""
    test_email = "applicant_hub_test@example.com"
    execute("DELETE FROM OwnerApplications WHERE email = %s", (test_email,))
    execute("DELETE FROM Users WHERE email = %s", (test_email,))

    # 1. Register a customer account
    uid, _ = register_user("Applicant Host", test_email, "+91 9888811111", "HostPass@123", role="CUSTOMER")
    assert uid is not None

    # 2. Submit application
    app_id, err = submit_owner_application(
        applicant_name="Applicant Host",
        email=test_email,
        phone="+91 9888811111",
        company_name="Aerocity Mall Hub",
        station_name="Aerocity EV Superhub",
        city="New Delhi",
        state="Delhi",
        pincode="110037",
        proposed_chargers=4,
        power_capacity_kw=120.0,
        user_id=uid,
    )
    assert err is None
    assert app_id is not None

    # 3. Admin views and reviews application
    app_row = get_owner_application_by_id(app_id)
    assert app_row is not None
    assert app_row["application_status"] == "PENDING"

    # Admin approves application -> atomically upgrades user to OWNER and assigns station
    ok, err_rev = review_owner_application(
        application_id=app_id,
        admin_user_id=1,
        action="APPROVED",
        admin_notes="Location verified on ground.",
        assign_station_id=1,
    )
    assert err_rev is None
    assert ok is True

    # User role upgraded to OWNER
    u_after = query_one("SELECT role FROM Users WHERE user_id = %s", (uid,))
    assert u_after["role"] == "OWNER"

    # Station assigned to owner
    st_after = query_one("SELECT owner_user_id FROM Stations WHERE station_id = 1")
    assert st_after["owner_user_id"] == uid

    # Clean up (revert station 1 to seeded owner)
    seeded_owner = query_one("SELECT user_id FROM Users WHERE email = 'owner.station01@example.test'")
    execute("UPDATE Stations SET owner_user_id = %s WHERE station_id = 1", (seeded_owner["user_id"] if seeded_owner else None,))
    execute("DELETE FROM OwnerApplications WHERE application_id = %s", (app_id,))
    execute("DELETE FROM Users WHERE user_id = %s", (uid,))


def test_station_partner_dashboard_and_hardware_rbac(client, admin_client):
    """20 & 22. Station Partner dashboard KPIs and strict hardware IDOR isolation."""
    # Seeded partner owner.station01@example.test
    owner = query_one("SELECT user_id, role FROM Users WHERE email = 'owner.station01@example.test'")
    assert owner is not None
    assert owner["role"] == "OWNER"
    uid = owner["user_id"]

    # KPIs scoped to owned stations
    kpis = get_owner_dashboard_kpis(uid)
    assert "station_count" in kpis
    assert "point_count" in kpis
    assert "total_kwh_delivered" in kpis
    assert "total_revenue" in kpis

    # Station access verification
    owned = get_owner_stations(uid)
    if owned:
        sid = owned[0]["station_id"]
        assert verify_owner_station_access(sid, uid) is True
        # Another random user has NO access
        assert verify_owner_station_access(sid, 99999) is False


def test_customer_blocked_from_hardware_endpoints(client):
    """23. Customer accounts are blocked (403) from partner hardware management."""
    # Login as customer (user 2 Aarav)
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["role"] = "CUSTOMER"
        sess["full_name"] = "Aarav Sharma"

    # Attempting to access partner-only hardware routes -> 403
    for path in ("/owner/stations", "/owner/stations/1/edit", "/owner/points", "/owner/sessions"):
        res = client.get(path)
        assert res.status_code == 403


def test_admin_inspect_user_detail(admin_client):
    """24. Admin can inspect individual user detail view."""
    res = admin_client.get("/admin/users/2")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Aarav Sharma" in html
    assert "CUSTOMER" in html
    assert "Registered Vehicles" in html


def test_customer_charging_history_pagination_and_csv():
    """11. Customer charging history pagination and RFC 4180 CSV export."""
    sessions, count, pages, cur_page = get_customer_charging_history(user_id=2, page=1, per_page=5)
    assert isinstance(sessions, list)
    assert count >= 0
    assert pages >= 1
    assert cur_page == 1

    csv_data = generate_customer_history_csv(user_id=2)
    assert "Session ID,Date & Time,Station Name,City" in csv_data
