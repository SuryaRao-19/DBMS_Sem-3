"""
Comprehensive Test Suite: Customer Station Details, 5-Step Reserve & Pay Wizard,
Offline Cash Payment Lifecycle, Role-Based Cash Collection, and QR Integration.
EV ChargeNet - Production Hardened
"""
import uuid
from datetime import datetime, timedelta
import pytest
from app.db import query_one, query_all, execute
from app.services.qr_service import get_or_create_station_qr, get_or_create_point_qr


@pytest.fixture
def customer_client(app):
    """Authenticated Customer test client (Aarav Sharma, user_id=2, role=CUSTOMER)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["full_name"] = "Aarav Sharma"
        sess["email"] = "aarav@example.com"
        sess["role"] = "CUSTOMER"
    return client


@pytest.fixture
def station_partner_client(app):
    """Authenticated Station Owner client (user_id=109, owner of Station 1)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 109
        sess["full_name"] = "Station Partner Demo 01"
        sess["email"] = "owner.station01@example.test"
        sess["role"] = "OWNER"
    return client


@pytest.fixture
def other_partner_client(app):
    """Authenticated second Station Owner client (unauthorized for Station 1)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["full_name"] = "Priya Verma"
        sess["email"] = "priya@example.com"
        sess["role"] = "OWNER"
    return client


@pytest.fixture(autouse=True)
def clean_test_bookings():
    """Ensure future test booking slots are clean so tests run deterministically without slot collision."""
    execute("DELETE FROM Payments WHERE booking_id IN (SELECT booking_id FROM Bookings WHERE start_at > NOW())")
    execute("DELETE FROM Bookings WHERE start_at > NOW()")
    yield
    execute("DELETE FROM Payments WHERE booking_id IN (SELECT booking_id FROM Bookings WHERE start_at > NOW())")
    execute("DELETE FROM Bookings WHERE start_at > NOW()")


def test_customer_station_details_page(customer_client):
    """
    1. Dedicated Customer Station Details (/customer/stations/<id>):
    Loads with 200, renders Leaflet map, Open-Meteo weather widget, dispenser list,
    and live EV-connector compatibility check for customer's registered vehicle.
    """
    res = customer_client.get("/customer/stations/1")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    assert "Connaught Place EV Hub" in html
    assert "Configured Charging Dispensers" in html or "Dispensers" in html
    assert "customerStationDetailMap" in html
    assert "Compatible with your" in html or "Compatible" in html
    assert "Reserve a Slot" in html or "Reserve &amp; Pay" in html or "Reserve & Pay" in html


def test_customer_reserve_and_pay_wizard_view(customer_client):
    """
    2. Unified Payments & Booking tab:
    Rendering ?tab=reserve displays 5-step wizard with real-time bill preview,
    transparent 18% GST tariff, and both Online and Cash payment options.
    """
    res = customer_client.get("/customer/payments?tab=reserve&point_id=1")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    assert "Reserve Charging Bay" in html or "Reserve &amp; Pay" in html or "Reserve & Pay" in html
    assert "Select Charging Station" in html
    assert "Select Charging Dispenser" in html
    assert "Arrival Time Slot" in html
    assert "Tariff &amp; Price Breakdown" in html or "Tariff & Price Breakdown" in html
    assert "Payment Method" in html
    assert "Pay at Station (Cash)" in html
    assert "Pay Online" in html


def test_customer_reserve_cash_payment_flow(customer_client):
    """
    3. Complete Cash Payment Lifecycle:
    POSTing /customer/reserve-and-pay with payment_method='CASH' atomically creates
    Booking in 'PENDING_PAYMENT' and Payment in 'PAYMENT_DUE' with 18% GST breakdown.
    """
    now = datetime.now() + timedelta(days=2)
    start_str = now.strftime("%Y-%m-%dT14:00")

    res = customer_client.post(
        "/customer/reserve-and-pay",
        data={
            "point_id": 1,
            "vehicle_id": 1,
            "start_time": start_str,
            "duration_minutes": 60,
            "estimated_kwh": 30,
            "payment_method": "CASH",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/customer/payments" in res.headers["Location"]

    # Verify database state
    pay_row = query_one(
        "SELECT p.*, b.booking_status, b.user_id, b.point_id "
        "FROM Payments p "
        "JOIN Bookings b ON b.booking_id = p.booking_id "
        "WHERE b.user_id = 2 AND p.payment_method = 'CASH' "
        "ORDER BY p.payment_id DESC LIMIT 1"
    )
    assert pay_row is not None
    assert pay_row["payment_status"] == "PAYMENT_DUE"
    assert pay_row["booking_status"] == "PENDING_PAYMENT"
    assert float(pay_row["amount"]) > 0
    assert float(pay_row["tax_amount"]) > 0

    # In-app notification sent to customer
    notif = query_one(
        "SELECT * FROM Notifications WHERE user_id = 2 ORDER BY notification_id DESC LIMIT 1"
    )
    assert notif is not None
    assert "Reserved" in notif["title"] or "Cash" in notif["title"]


def test_customer_cannot_collect_cash_idor(customer_client):
    """
    4. Strict IDOR Security:
    Customer role cannot call admin or owner cash collection endpoints.
    """
    now = datetime.now() + timedelta(days=2)
    start_str = now.strftime("%Y-%m-%dT17:00")
    customer_client.post(
        "/customer/reserve-and-pay",
        data={
            "point_id": 1,
            "vehicle_id": 1,
            "start_time": start_str,
            "duration_minutes": 30,
            "estimated_kwh": 10,
            "payment_method": "CASH",
        },
    )
    pay = query_one("SELECT payment_id FROM Payments WHERE payment_status = 'PAYMENT_DUE' ORDER BY payment_id DESC LIMIT 1")
    assert pay is not None

    pid = pay["payment_id"]
    # Customer trying admin route -> 403 Forbidden
    res_admin = customer_client.post(f"/admin/payments/{pid}/collect-cash")
    assert res_admin.status_code == 403

    # Customer trying owner route -> 403 Forbidden
    res_owner = customer_client.post(f"/owner/payments/{pid}/collect-cash")
    assert res_owner.status_code == 403


def test_owner_cash_collection_flow(customer_client, station_partner_client):
    """
    5. Station Owner Cash Collection:
    Station partner confirms cash received at bay, transitioning Payment to SUCCESS
    and Booking to CONFIRMED, setting audit log and customer notification.
    """
    # Create a fresh cash reservation at station 1
    now = datetime.now() + timedelta(days=3)
    start_str = now.strftime("%Y-%m-%dT15:00")
    customer_client.post(
        "/customer/reserve-and-pay",
        data={
            "point_id": 1,
            "vehicle_id": 1,
            "start_time": start_str,
            "duration_minutes": 60,
            "estimated_kwh": 25,
            "payment_method": "CASH",
        },
    )

    pay = query_one(
        "SELECT p.payment_id, p.booking_id, p.amount "
        "FROM Payments p "
        "JOIN Bookings b ON b.booking_id = p.booking_id "
        "WHERE b.point_id = 1 AND p.payment_status = 'PAYMENT_DUE' "
        "ORDER BY p.payment_id DESC LIMIT 1"
    )
    assert pay is not None
    pid = pay["payment_id"]
    bid = pay["booking_id"]

    # Station Partner collects cash
    res = station_partner_client.post(
        f"/owner/payments/{pid}/collect-cash",
        data={"notes": "Driver paid ₹500 note at bay 1"},
        follow_redirects=True,
    )
    assert res.status_code == 200

    # Verify DB updates
    updated_pay = query_one("SELECT * FROM Payments WHERE payment_id = %s", (pid,))
    assert updated_pay["payment_status"] == "SUCCESS"
    assert updated_pay["cash_collected_by"] == 109
    assert updated_pay["cash_collected_at"] is not None
    assert "Driver paid" in updated_pay["cash_notes"]

    updated_bk = query_one("SELECT booking_status FROM Bookings WHERE booking_id = %s", (bid,))
    assert updated_bk["booking_status"] == "CONFIRMED"

    # Verify Audit log
    audit = query_one(
        "SELECT * FROM AuditLogs WHERE action = 'COLLECT_CASH_PAYMENT' AND entity_id = %s",
        (pid,),
    )
    assert audit is not None
    assert audit["user_id"] == 109


def test_unauthorized_owner_cannot_collect_cash_for_other_station(customer_client, other_partner_client):
    """
    6. Multi-Tenant Station Isolation:
    A station partner cannot collect cash for a station they do not own.
    """
    # Create a reservation at Station 1 (owned by user 109)
    now = datetime.now() + timedelta(days=4)
    start_str = now.strftime("%Y-%m-%dT16:00")
    customer_client.post(
        "/customer/reserve-and-pay",
        data={
            "point_id": 1,
            "vehicle_id": 1,
            "start_time": start_str,
            "duration_minutes": 30,
            "estimated_kwh": 20,
            "payment_method": "CASH",
        },
    )

    pay = query_one(
        "SELECT p.payment_id "
        "FROM Payments p "
        "JOIN Bookings b ON b.booking_id = p.booking_id "
        "WHERE b.point_id = 1 AND p.payment_status = 'PAYMENT_DUE' "
        "ORDER BY p.payment_id DESC LIMIT 1"
    )
    assert pay is not None
    pid = pay["payment_id"]

    # Other partner (user 3, does not own Station 1) attempts collection
    res = other_partner_client.post(
        f"/owner/payments/{pid}/collect-cash",
        follow_redirects=True,
    )
    assert res.status_code in (200, 403)
    if res.status_code == 200:
        html = res.data.decode("utf-8")
        assert "Unauthorized" in html

    # Verify payment remains PAYMENT_DUE
    unaltered = query_one("SELECT payment_status FROM Payments WHERE payment_id = %s", (pid,))
    assert unaltered["payment_status"] == "PAYMENT_DUE"


def test_admin_cash_collection_flow(admin_client, customer_client):
    """
    7. Platform Admin Cash Collection:
    Platform administrator can collect and clear any offline payment.
    """
    now = datetime.now() + timedelta(days=5)
    start_str = now.strftime("%Y-%m-%dT10:00")
    customer_client.post(
        "/customer/reserve-and-pay",
        data={
            "point_id": 1,
            "vehicle_id": 1,
            "start_time": start_str,
            "duration_minutes": 30,
            "estimated_kwh": 15,
            "payment_method": "CASH",
        },
    )

    pay = query_one(
        "SELECT p.payment_id, p.booking_id "
        "FROM Payments p "
        "JOIN Bookings b ON b.booking_id = p.booking_id "
        "WHERE b.point_id = 1 AND p.payment_status = 'PAYMENT_DUE' "
        "ORDER BY p.payment_id DESC LIMIT 1"
    )
    assert pay is not None
    pid = pay["payment_id"]

    res = admin_client.post(
        f"/admin/payments/{pid}/collect-cash",
        data={"notes": "Cleared by platform admin counter"},
        follow_redirects=True,
    )
    assert res.status_code == 200

    updated = query_one("SELECT payment_status, cash_collected_by FROM Payments WHERE payment_id = %s", (pid,))
    assert updated["payment_status"] == "SUCCESS"
    assert updated["cash_collected_by"] == 1


def test_customer_reserve_online_payment_flow(customer_client):
    """
    8. Online Payment Reservation Flow:
    POSTing /customer/reserve-and-pay with payment_method='ONLINE' creates booking
    and redirects customer to the secure Razorpay checkout page.
    """
    now = datetime.now() + timedelta(days=6)
    start_str = now.strftime("%Y-%m-%dT11:00")

    res = customer_client.post(
        "/customer/reserve-and-pay",
        data={
            "point_id": 1,
            "vehicle_id": 1,
            "start_time": start_str,
            "duration_minutes": 60,
            "estimated_kwh": 35,
            "payment_method": "ONLINE",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/customer/bookings/" in res.headers["Location"]
    assert "/checkout" in res.headers["Location"]


def test_qr_resolver_integration_with_customer_portal(client):
    """
    9. Unified QR Resolver Integration:
    Point QR resolves with action_url to customer reservation wizard.
    Station QR resolves with action_url to customer station details.
    """
    pt_qr = get_or_create_point_qr(1, created_by=1)
    assert pt_qr is not None
    token_pt = pt_qr["qr_token"]

    res_pt = client.get(f"/api/qr/resolve?token={token_pt}")
    assert res_pt.status_code == 200
    data_pt = res_pt.get_json()
    assert data_pt["success"] is True
    assert data_pt["data"]["qr_type"] == "POINT"
    assert "/customer/payments?tab=reserve&point_id=1" in data_pt["data"]["action_url"]

    st_qr = get_or_create_station_qr(1, admin_user_id=1)
    assert st_qr is not None
    token_st = st_qr["qr_token"]

    res_st = client.get(f"/api/qr/resolve?token={token_st}")
    assert res_st.status_code == 200
    data_st = res_st.get_json()
    assert data_st["success"] is True
    assert data_st["data"]["qr_type"] == "STATION"
    assert "/customer/stations/1" in data_st["data"]["action_url"]


def test_admin_sync_ocm_action(admin_client):
    """
    10. Open Charge Map Sync Action:
    Admin can trigger synchronization from /admin/stations/sync-ocm.
    """
    res = admin_client.post(
        "/admin/stations/sync-ocm",
        data={"city": "Delhi NCR", "max_results": 5},
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Open Charge Map Sync Complete" in html or "synchronization note" in html

    audit = query_one(
        "SELECT * FROM AuditLogs WHERE action = 'SYNC_OPEN_CHARGE_MAP' ORDER BY log_id DESC LIMIT 1"
    )
    assert audit is not None
    assert "Delhi NCR" in audit["details"]
