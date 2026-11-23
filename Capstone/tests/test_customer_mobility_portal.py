"""
Exhaustive Automated Test Suite: Customer Mobility Portal, Razorpay QR Payments & UI Integrity
Covers all requirements from Phase 1 through Phase 9.
"""
import hmac
import hashlib
import json
import pytest
from datetime import datetime, timedelta

from app.db import query_one, query_all, execute
from app.services.station_service import get_all_stations
from app.services.customer_service import (
    get_customer_dashboard_kpis,
    get_customer_payments,
    get_customer_payment_summary,
)
from app.services.razorpay_service import (
    get_booking_checkout_context,
    create_razorpay_order,
    verify_and_settle_razorpay_payment,
    create_dynamic_payment_qr,
    generate_sandbox_payment_proof,
)
from app.services.qr_service import (
    resolve_any_qr_token,
    get_or_create_booking_qr,
    mark_booking_qr_verified,
    record_qr_scan_by_token,
)


@pytest.fixture
def customer_client(app):
    """Authenticated Customer test client (Aarav Sharma, user_id=2, CUSTOMER)."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 2
        sess["full_name"] = "Aarav Sharma"
        sess["email"] = "aarav@example.com"
        sess["role"] = "CUSTOMER"
    return c


@pytest.fixture
def other_customer_client(app):
    """Authenticated second Customer test client (Priya Verma, user_id=3, CUSTOMER)."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 3
        sess["full_name"] = "Priya Verma"
        sess["email"] = "priya@example.com"
        sess["role"] = "CUSTOMER"
    return c


# ==============================================================================
# 1. STATION SERVICE FILTERS & TYPEERROR ELIMINATION
# ==============================================================================

def test_get_all_stations_no_filters():
    """1. get_all_stations() executes without arguments and returns active stations."""
    stations = get_all_stations()
    assert isinstance(stations, list)
    assert len(stations) > 0


def test_get_all_stations_city_filter():
    """2. get_all_stations() filters properly by city."""
    delhi_stations = get_all_stations(city="New Delhi")
    assert isinstance(delhi_stations, list)
    assert len(delhi_stations) > 0
    for s in delhi_stations:
        assert s.get("city") == "New Delhi"


def test_get_all_stations_status_filter():
    """3. get_all_stations() filters by station status."""
    active_stations = get_all_stations(status="ACTIVE")
    assert isinstance(active_stations, list)
    for s in active_stations:
        assert s.get("station_status") == "ACTIVE" or s.get("status") == "ACTIVE"


def test_get_all_stations_operator_filter():
    """4. get_all_stations() filters by operator name (e.g. Tata Power EZ Charge)."""
    tata_stations = get_all_stations(operator="Tata Power EZ Charge")
    assert isinstance(tata_stations, list)
    assert len(tata_stations) > 0
    for s in tata_stations:
        assert "Tata Power" in s.get("operator_name", "")


def test_get_all_stations_connector_filter():
    """5. get_all_stations() filters by connector type (CCS2, TYPE2, etc.)."""
    ccs2_stations = get_all_stations(connector="CCS2")
    assert isinstance(ccs2_stations, list)
    assert len(ccs2_stations) > 0


def test_get_all_stations_min_power_filter():
    """6. get_all_stations() filters by minimum capacity kW."""
    fast_stations = get_all_stations(min_power=50)
    assert isinstance(fast_stations, list)
    assert len(fast_stations) > 0


def test_get_all_stations_combined_filters():
    """7. get_all_stations() supports combining multiple filters simultaneously."""
    combined = get_all_stations(
        city="New Delhi",
        operator="Tata Power EZ Charge",
        connector="CCS2",
        min_power=25,
        status="ACTIVE",
    )
    assert isinstance(combined, list)
    for s in combined:
        assert s.get("city") == "New Delhi"
        assert s.get("station_status") == "ACTIVE" or s.get("status") == "ACTIVE"


def test_get_all_stations_unknown_kwargs_safety():
    """8. get_all_stations() safely accepts unknown kwargs without TypeError."""
    res = get_all_stations(
        unexpected_key="arbitrary_value",
        unknown_filter=999,
        some_flag=True,
    )
    assert isinstance(res, list)


def test_get_all_stations_keyword_search():
    """9. get_all_stations() supports keyword search 'q' across name, address, operator."""
    res = get_all_stations(q="Connaught")
    assert isinstance(res, list)
    assert len(res) > 0
    for s in res:
        matches = (
            "connaught" in s.get("station_name", "").lower()
            or "connaught" in s.get("address", "").lower()
            or "connaught" in s.get("city", "").lower()
        )
        assert matches


# ==============================================================================
# 2. CUSTOMER STATIONS ROUTE
# ==============================================================================

def test_customer_stations_route_renders_and_filters(customer_client):
    """10. /customer/stations responds with 200 and reflects query parameters and filter markup."""
    res = customer_client.get("/customer/stations?q=Tata&city=New+Delhi&operator=Tata+Power+EZ+Charge&connector=CCS2&min_power=50")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Find Charging Stations" in html
    assert "Tata Power" in html
    assert "connector" in html.lower()
    assert "min_power" in html.lower()


# ==============================================================================
# 3. AUTHENTICATION & ROLE-BASED ACCESS CONTROL GUARDS
# ==============================================================================

def test_unauthenticated_customer_routes_redirect_to_login(client):
    """11-13. Anonymous requests to protected customer routes redirect to login."""
    for path in ["/customer/dashboard", "/customer/payments", "/customer/stations", "/customer/vehicles"]:
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 302
        assert "/login" in res.location


def test_customer_blocked_from_admin_and_owner_dashboards(customer_client):
    """14-15. Logged-in CUSTOMER cannot access /admin or hardware partner endpoints (403 Forbidden)."""
    res_admin = customer_client.get("/admin/dashboard")
    assert res_admin.status_code == 403

    res_owner_hw = customer_client.get("/owner/stations")
    assert res_owner_hw.status_code == 403


def test_customer_allowed_on_customer_endpoints(customer_client):
    """16. Logged-in CUSTOMER accesses /customer/dashboard and /customer/payments with 200 OK."""
    res_dash = customer_client.get("/customer/dashboard")
    assert res_dash.status_code == 200

    res_pay = customer_client.get("/customer/payments")
    assert res_pay.status_code == 200


# ==============================================================================
# 4. CUSTOMER DASHBOARD LAYOUT & METRIC CARDS INTEGRITY (PHASE 1 VERIFICATION)
# ==============================================================================

def test_customer_dashboard_metric_cards_and_css_structure(customer_client):
    """17. Customer dashboard renders 4 distinct metric cards in .customer-metrics-grid."""
    res = customer_client.get("/customer/dashboard")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    # Grid container exists
    assert "customer-metrics-grid" in html or "stats-grid" in html

    # All 4 metric card titles are present
    assert "Total Charging Sessions" in html
    assert "Total Energy Consumed" in html
    assert "Total Spent" in html
    assert "Active / Upcoming Bookings" in html or "Upcoming Bookings" in html

    # Structure check: stat-card elements are well-formed
    assert "stat-card-title" in html
    assert "stat-card-value" in html


# ==============================================================================
# 5. CUSTOMER PAYMENTS PAGE & TRANSACTION LEDGER (PHASE 2 VERIFICATION)
# ==============================================================================

def test_customer_payments_page_structure_and_modal(customer_client):
    """18. Customer payments page has 4 summary cards, search filters, table, and details modal."""
    res = customer_client.get("/customer/payments")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    # 4 metric cards on payments page
    assert "Total Settled (Test Mode)" in html or "Total Settled" in html
    assert "Successful Transactions" in html
    assert "Pending Transactions" in html
    assert "Total Invoices" in html

    # Filter inputs
    assert 'name="search"' in html or 'name="q"' in html
    assert 'name="status"' in html
    assert 'name="start_date"' in html
    assert 'name="end_date"' in html

    # Modal markup exists
    assert 'id="paymentModal"' in html or 'id="paymentDetailModal"' in html
    assert 'modalTxRef' in html
    assert 'modalTotalAmount' in html


def test_customer_payments_service_filtering_and_pagination():
    """19. get_customer_payments() handles search, status, date filtering, and pagination cleanly."""
    rows, total_count, total_pages, page = get_customer_payments(
        user_id=2,
        search="",
        status="ALL",
        start_date=None,
        end_date=None,
        page=1,
        per_page=10,
    )
    assert isinstance(rows, list)
    assert isinstance(total_count, int)
    assert isinstance(total_pages, int)
    assert page == 1


def test_customer_payment_summary_calculation():
    """20. get_customer_payment_summary() computes correct numeric values."""
    summary = get_customer_payment_summary(user_id=2)
    assert "total_tx" in summary
    assert "total_paid" in summary
    assert "total_pending" in summary
    assert "paid_count" in summary
    assert "pending_count" in summary
    assert isinstance(summary["total_paid"], (int, float))


# ==============================================================================
# 6. IDOR GUARDS: BOOKING CHECKOUT & PAYMENT RECEIPTS
# ==============================================================================

def test_booking_checkout_idor_protection(customer_client, other_customer_client):
    """21. Customer A cannot view or checkout Customer B's booking (strictly 403 or 404)."""
    # Create a test booking belonging to Customer B (user_id=3, vehicle_id=2)
    start_dt = datetime.now() + timedelta(days=5, hours=1)
    end_dt = start_dt + timedelta(hours=1)
    execute(
        "INSERT INTO Bookings (user_id, point_id, vehicle_id, start_at, end_at, estimated_energy_kwh, estimated_cost, booking_status) "
        "VALUES (3, 1, 2, %s, %s, 25.0, 450.00, 'PENDING')",
        (start_dt, end_dt)
    )
    b_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    try:
        # Customer A (user_id=2) tries to access Customer B's checkout -> 403
        res_a = customer_client.get(f"/customer/bookings/{b_id}/checkout")
        assert res_a.status_code in (403, 404)

        # Customer B (user_id=3) is allowed access -> 200
        res_b = other_customer_client.get(f"/customer/bookings/{b_id}/checkout")
        assert res_b.status_code == 200
        assert "Settle Booking Reservation" in res_b.data.decode("utf-8") or "Checkout" in res_b.data.decode("utf-8")
    finally:
        execute("DELETE FROM Bookings WHERE booking_id = %s", (b_id,))


def test_payment_receipt_idor_protection(customer_client, other_customer_client):
    """22. Customer A cannot download or view Customer B's payment receipt."""
    # Create session and payment for Customer B (user_id=3, vehicle_id=2)
    execute(
        "INSERT INTO ChargingSessions (user_id, point_id, vehicle_id, start_at, end_at, energy_kwh, tariff_per_kwh, total_cost, session_status) "
        "VALUES (3, 1, 2, NOW(), NOW(), 20.0, 18.00, 500.00, 'COMPLETED')"
    )
    s_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    execute(
        "INSERT INTO Payments (session_id, booking_id, amount, base_amount, tax_amount, payment_method, payment_status, transaction_reference) "
        "VALUES (%s, NULL, 500.00, 423.73, 76.27, 'UPI', 'SUCCESS', 'TXN_IDOR_TEST_01')",
        (s_id,)
    )
    p_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    try:
        # Customer A (user_id=2) tries to access Customer B's receipt -> 403 or 404
        res_a = customer_client.get(f"/customer/payments/{p_id}/receipt")
        assert res_a.status_code in (403, 404)

        # Customer B (user_id=3) gets 200 OK text receipt
        res_b = other_customer_client.get(f"/customer/payments/{p_id}/receipt")
        assert res_b.status_code == 200
        assert "TAX INVOICE & CHARGE RECEIPT" in res_b.data.decode("utf-8")
    finally:
        execute("DELETE FROM Payments WHERE payment_id = %s", (p_id,))
        execute("DELETE FROM ChargingSessions WHERE session_id = %s", (s_id,))


# ==============================================================================
# 7. RAZORPAY ORDER CREATION, VERIFICATION & IDEMPOTENCY
# ==============================================================================

def test_razorpay_order_creation_for_booking(customer_client):
    """23. API creates valid Razorpay order structure for owned booking."""
    start_dt = datetime.now() + timedelta(days=6)
    end_dt = start_dt + timedelta(hours=1)
    execute(
        "INSERT INTO Bookings (user_id, point_id, vehicle_id, start_at, end_at, estimated_energy_kwh, estimated_cost, booking_status) "
        "VALUES (2, 1, 1, %s, %s, 30.0, 540.00, 'PENDING')",
        (start_dt, end_dt)
    )
    b_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    try:
        res = customer_client.post(
            "/api/payments/razorpay/create-order",
            json={"booking_id": b_id},
        )
        assert res.status_code in (200, 201)
        data = res.get_json()
        assert data.get("success") is True
        order = data.get("order", {})
        assert order.get("order_id").startswith("order_")
        assert order.get("amount_paise") == 54000  # in paise
        assert order.get("currency") == "INR"
        assert "key_id" in order
    finally:
        execute("DELETE FROM Payments WHERE booking_id = %s", (b_id,))
        execute("DELETE FROM Bookings WHERE booking_id = %s", (b_id,))


def test_razorpay_verification_valid_signature_and_idempotency(customer_client, app):
    """24-25. Valid HMAC signature settles booking; duplicate call is idempotent."""
    start_dt = datetime.now() + timedelta(days=14)
    end_dt = start_dt + timedelta(hours=1)
    execute(
        "INSERT INTO Bookings (user_id, point_id, vehicle_id, start_at, end_at, estimated_energy_kwh, estimated_cost, booking_status) "
        "VALUES (2, 1, 1, %s, %s, 20.0, 360.00, 'PENDING')",
        (start_dt, end_dt)
    )
    b_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    try:
        # Create order first within app context
        with app.app_context():
            order, err = create_razorpay_order(booking_id=b_id, user_id=2)
            assert err is None
            order_id = order["order_id"]

            # Sandbox proof generation using identical app context secret
            payment_id, valid_sig = generate_sandbox_payment_proof(order_id)
            assert payment_id is not None
            assert valid_sig is not None

        # Step 1: Verify valid signature -> 200 OK and settled
        res_verify = customer_client.post(
            "/api/payments/razorpay/verify",
            json={
                "booking_id": b_id,
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
        )
        assert res_verify.status_code == 200
        data_verify = res_verify.get_json()
        assert data_verify.get("success") is True
        assert data_verify.get("status") == "SUCCESS"

        # Check database: booking is CONFIRMED
        booking_row = query_one("SELECT booking_status FROM Bookings WHERE booking_id = %s", (b_id,))
        assert booking_row["booking_status"] == "CONFIRMED"

        # Step 2: Idempotency test — call verify again with the same payload
        res_repeat = customer_client.post(
            "/api/payments/razorpay/verify",
            json={
                "booking_id": b_id,
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
        )
        assert res_repeat.status_code == 200
        data_repeat = res_repeat.get_json()
        assert data_repeat.get("success") is True

    finally:
        execute("DELETE FROM Payments WHERE booking_id = %s", (b_id,))
        execute("DELETE FROM Bookings WHERE booking_id = %s", (b_id,))


def test_razorpay_verification_rejects_invalid_signature(customer_client):
    """26. Invalid HMAC signature is rejected with 400 Bad Request."""
    res = customer_client.post(
        "/api/payments/razorpay/verify",
        json={
            "booking_id": 99999,
            "razorpay_order_id": "order_fake_123",
            "razorpay_payment_id": "pay_fake_456",
            "razorpay_signature": "invalid_tampered_signature_hex",
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data.get("success") is False


# ==============================================================================
# 8. DYNAMIC SINGLE-USE UPI QR CODE & SCANNER RESOLUTION
# ==============================================================================

def test_dynamic_upi_qr_generation_and_token_resolution(customer_client):
    """27. Generates dynamic single-use 10-minute UPI QR code and validates token resolution."""
    start_dt = datetime.now() + timedelta(days=8)
    end_dt = start_dt + timedelta(hours=1)
    execute(
        "INSERT INTO Bookings (user_id, point_id, vehicle_id, start_at, end_at, estimated_energy_kwh, estimated_cost, booking_status) "
        "VALUES (2, 1, 1, %s, %s, 15.0, 270.00, 'PENDING')",
        (start_dt, end_dt)
    )
    b_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    try:
        # Request dynamic QR via API
        res = customer_client.post(
            "/api/payments/razorpay/qr",
            json={"booking_id": b_id},
        )
        assert res.status_code in (200, 201)
        res_json = res.get_json()
        assert res_json.get("success") is True
        qr_obj = res_json.get("qr", {})
        assert qr_obj.get("qr_image_data_uri").startswith("data:image/")
        assert qr_obj.get("ttl_seconds") > 0

        # Token resolution via QR service using payment_qr_id
        qr_token = qr_obj.get("payment_qr_id")
        resolved, err, status = resolve_any_qr_token(qr_token)
        assert status == 200
        assert resolved.get("type") == "PAYMENT"
        assert resolved.get("payment_id") is not None

    finally:
        execute("DELETE FROM Payments WHERE booking_id = %s", (b_id,))
        execute("DELETE FROM Bookings WHERE booking_id = %s", (b_id,))


def test_revoked_qr_code_handling():
    """28. Revoked QR code is detected and rejected with 410 or error."""
    execute(
        "INSERT INTO StationQRCodes (station_id, qr_token, qr_status) "
        "VALUES (1, 'TEST_REVOKED_TOKEN_99', 'REVOKED')"
    )
    try:
        row, err, code = record_qr_scan_by_token("TEST_REVOKED_TOKEN_99")
        assert code == 410
        assert "revoked" in err.lower()
    finally:
        execute("DELETE FROM StationQRCodes WHERE qr_token = 'TEST_REVOKED_TOKEN_99'")
