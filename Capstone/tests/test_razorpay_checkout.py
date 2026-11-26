"""
Razorpay TEST MODE Integration, Security Guardrail, Webhook & UI Redesign Tests
Tata Power EZ Charge — EV Network Management Demo
"""
import hashlib
import hmac
import json
import uuid
import pytest

from app.db import execute, query_one, query_all
from app.services.session_service import start_session, complete_session
from app.services.razorpay_service import (
    is_live_razorpay_key,
    verify_payment_signature,
    verify_webhook_signature,
    process_razorpay_webhook,
)


def _create_completed_test_session(user_id=2, vehicle_id=1, point_id=1, energy_kwh=12.500):
    """Create and complete an isolated charging session for checkout testing."""
    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = %s", (point_id,))
    execute("DELETE FROM ChargingSessions WHERE user_id = %s AND session_status = 'IN_PROGRESS'", (user_id,))
    sid, err = start_session(user_id=user_id, vehicle_id=vehicle_id, point_id=point_id)
    assert err is None and sid is not None
    completed, err2 = complete_session(session_id=sid, energy_kwh=energy_kwh, user_id=user_id)
    assert err2 is None and completed is not None
    return sid, completed


def _cleanup_test_session(session_id, point_id=1):
    """Remove test payment, webhook audit, and session artifacts after test completion."""
    rows = query_all("SELECT razorpay_order_id FROM Payments WHERE session_id = %s", (session_id,))
    for r in rows:
        oid = r.get("razorpay_order_id")
        if oid:
            execute("DELETE FROM PaymentWebhookEvents WHERE razorpay_order_id = %s", (oid,))
    execute("DELETE FROM Payments WHERE session_id = %s", (session_id,))
    execute("DELETE FROM ChargingSessions WHERE session_id = %s", (session_id,))
    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = %s", (point_id,))


def test_razorpay_live_key_guardrail():
    """Live Razorpay keys (rzp_live_*) must be strictly blocked by default."""
    assert is_live_razorpay_key("rzp_live_1234567890abcdef") is True
    assert is_live_razorpay_key("rzp_test_1234567890abcdef") is False
    assert is_live_razorpay_key("") is False


def test_razorpay_checkout_page_renders_and_blocks_idor(owner_client, other_owner_client):
    """Dedicated checkout page must show GST breakdown, TEST MODE notice, no secrets, and enforce IDOR."""
    sid, completed = _create_completed_test_session()
    try:
        res = owner_client.get(f"/owner/checkout/{sid}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "TEST MODE ONLY" in html
        assert "GST (18% Included)" in html
        assert "RAZORPAY_KEY_SECRET" not in html
        assert "RAZORPAY_WEBHOOK_SECRET" not in html
        assert f"Session #{sid}" in html

        # Cross-user IDOR attempt returns strict 403 Forbidden
        res_other = other_owner_client.get(f"/owner/checkout/{sid}")
        assert res_other.status_code == 403
    finally:
        _cleanup_test_session(sid)


def test_razorpay_order_verify_and_sandbox_complete_flow(owner_client, other_owner_client):
    """
    Verify server-calculated order creation, signature forgery rejection,
    ownership enforcement, and sandbox cryptographic settlement.
    """
    sid, completed = _create_completed_test_session(energy_kwh=20.000)
    try:
        # 1. Cross-user order creation blocked with 403
        cross_res = other_owner_client.post(
            "/api/payments/razorpay/order",
            json={"session_id": sid, "payment_method": "UPI"},
        )
        assert cross_res.status_code == 403

        # 2. Owner creates Razorpay test order (server-computed total & 18% GST breakdown)
        res = owner_client.post(
            "/api/payments/razorpay/order",
            json={"session_id": sid, "payment_method": "UPI"},
        )
        assert res.status_code == 201
        payload = res.get_json()
        assert payload["success"] is True
        assert payload["mode"] == "TEST_MODE"
        order = payload["order"]
        order_id = order["order_id"]
        assert order_id.startswith("order_sim_")
        expected_inr = round(float(completed["total_cost"]), 2)
        assert round(order["amount_inr"], 2) == expected_inr
        assert order["amount_paise"] == int(round(expected_inr * 100))
        assert round(order["base_amount"] + order["tax_amount"], 2) == expected_inr

        # 3. Forged signature rejected cleanly with 400 and does NOT settle payment
        bad_verify = owner_client.post(
            "/api/payments/razorpay/verify",
            json={
                "session_id": sid,
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_sim_forged1234",
                "razorpay_signature": "00000000000000000000000000000000forged",
                "payment_method": "UPI",
            },
        )
        assert bad_verify.status_code == 400
        pending_row = query_one("SELECT payment_status FROM Payments WHERE razorpay_order_id = %s", (order_id,))
        assert pending_row["payment_status"] == "PENDING"

        # 4. Sandbox completion generates valid HMAC signature and settles payment as RAZORPAY_TEST
        done_res = owner_client.post(
            "/api/payments/razorpay/sandbox-complete",
            json={"session_id": sid, "razorpay_order_id": order_id, "payment_method": "CARD"},
        )
        assert done_res.status_code == 200
        done_json = done_res.get_json()
        assert done_json["success"] is True
        assert done_json["status"] == "SUCCESS"
        assert done_json["razorpay_payment_id"].startswith("pay_sim_")

        settled_row = query_one(
            "SELECT payment_status, gateway_provider, razorpay_payment_id, razorpay_signature, payment_method "
            "FROM Payments WHERE razorpay_order_id = %s",
            (order_id,),
        )
        assert settled_row["payment_status"] == "SUCCESS"
        assert settled_row["gateway_provider"] == "RAZORPAY_TEST"
        assert settled_row["razorpay_payment_id"].startswith("pay_sim_")
        assert settled_row["razorpay_signature"]
        assert settled_row["payment_method"] == "CARD"

        # 5. Creating another order for already settled session is rejected
        dup_order = owner_client.post(
            "/api/payments/razorpay/order",
            json={"session_id": sid, "payment_method": "UPI"},
        )
        assert dup_order.status_code == 400
    finally:
        _cleanup_test_session(sid)


def test_razorpay_webhook_hmac_verification_and_idempotency(app, client, owner_client, monkeypatch):
    """
    Verify webhook endpoint validates X-Razorpay-Signature HMAC-SHA256,
    updates PENDING order on payment.captured, ignores duplicate replays via event_id,
    and refuses to downgrade an already SUCCESS order on out-of-order payment.failed.
    """
    webhook_secret = "test_rzp_webhook_secret_2026"
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", webhook_secret)

    sid, _ = _create_completed_test_session(energy_kwh=10.000)
    event_capture_id = f"evt_cap_{uuid.uuid4().hex[:10]}"
    event_fail_id = f"evt_fail_{uuid.uuid4().hex[:10]}"

    try:
        # Create PENDING order
        res = owner_client.post(
            "/api/payments/razorpay/order",
            json={"session_id": sid, "payment_method": "UPI"},
        )
        assert res.status_code == 201
        order_id = res.get_json()["order"]["order_id"]
        pay_id = f"pay_test_{uuid.uuid4().hex[:12]}"

        cap_body = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "order_id": order_id,
                        "status": "captured",
                    }
                }
            },
        }).encode("utf-8")

        # 1. Invalid webhook signature returns 401
        bad_wh = client.post(
            "/api/payments/razorpay/webhook",
            data=cap_body,
            content_type="application/json",
            headers={"X-Razorpay-Signature": "invalid_sig", "X-Razorpay-Event-Id": event_capture_id},
        )
        assert bad_wh.status_code == 401

        # 2. Valid HMAC-SHA256 signature captures PENDING order
        valid_sig = hmac.new(webhook_secret.encode("utf-8"), cap_body, hashlib.sha256).hexdigest()
        ok_wh = client.post(
            "/api/payments/razorpay/webhook",
            data=cap_body,
            content_type="application/json",
            headers={"X-Razorpay-Signature": valid_sig, "X-Razorpay-Event-Id": event_capture_id},
        )
        assert ok_wh.status_code == 200
        assert ok_wh.get_json()["status"] == "PROCESSED"

        row_after = query_one(
            "SELECT payment_status, razorpay_payment_id FROM Payments WHERE razorpay_order_id = %s",
            (order_id,),
        )
        assert row_after["payment_status"] == "SUCCESS"
        assert row_after["razorpay_payment_id"] == pay_id

        # 3. Duplicate delivery with same X-Razorpay-Event-Id is ignored idempotently
        dup_wh = client.post(
            "/api/payments/razorpay/webhook",
            data=cap_body,
            content_type="application/json",
            headers={"X-Razorpay-Signature": valid_sig, "X-Razorpay-Event-Id": event_capture_id},
        )
        assert dup_wh.status_code == 200
        assert dup_wh.get_json()["status"] == "DUPLICATE_IGNORED"

        events_count = query_one(
            "SELECT COUNT(*) AS cnt FROM PaymentWebhookEvents WHERE event_id = %s",
            (event_capture_id,),
        )["cnt"]
        assert events_count == 1

        # 4. Out-of-order payment.failed webhook does NOT downgrade an already SUCCESS order
        fail_body = json.dumps({
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "order_id": order_id,
                        "status": "failed",
                    }
                }
            },
        }).encode("utf-8")
        fail_sig = hmac.new(webhook_secret.encode("utf-8"), fail_body, hashlib.sha256).hexdigest()
        fail_wh = client.post(
            "/api/payments/razorpay/webhook",
            data=fail_body,
            content_type="application/json",
            headers={"X-Razorpay-Signature": fail_sig, "X-Razorpay-Event-Id": event_fail_id},
        )
        assert fail_wh.status_code == 200
        row_final = query_one(
            "SELECT payment_status FROM Payments WHERE razorpay_order_id = %s",
            (order_id,),
        )
        assert row_final["payment_status"] == "SUCCESS"
    finally:
        execute("DELETE FROM PaymentWebhookEvents WHERE event_id IN (%s, %s)", (event_capture_id, event_fail_id))
        _cleanup_test_session(sid)


def test_admin_dashboard_charts_sidebar_and_static_ev_media(client, admin_client):
    """
    Verify Phase 2 Admin collapsible sidebar, Phase 4 verified Tata Power EZ Charge stats + links,
    Phase 5 local EV image assets (HTTP 200), and Phase 11 real MySQL Chart.js analytics.
    """
    # 1. Public landing verifies official Tata Power EZ Charge stats & links
    res_home = client.get("/")
    assert res_home.status_code == 200
    home_html = res_home.data.decode("utf-8")
    assert "Power Every Journey." in home_html
    assert "Charge Smarter." in home_html
    assert "6,700+" in home_html
    assert "700+" in home_html
    assert "2.5 lakh+" in home_html
    assert "1,200+" in home_html
    assert "https://play.google.com/store/apps/details?id=com.tatapower.evapp" in home_html
    assert "https://apps.apple.com/in/app/tata-power-ez-charge/id1496350476" in home_html
    assert "https://linktr.ee/Tata_Power_EZ_Charge" in home_html

    # 2. All local EV photography and SVG logo serve HTTP 200 cleanly
    for img_path in (
        "/static/images/logo.svg",
        "/static/images/hero-ev-charging.jpg",
        "/static/images/dc-fast-charger.jpg",
        "/static/images/home-ac-charger.jpg",
        "/static/images/fleet-ebus-charging.jpg",
    ):
        img_res = client.get(img_path)
        assert img_res.status_code == 200, f"Missing or broken static media: {img_path}"
        assert len(img_res.data) > 400

    # 3. Admin dashboard renders fixed collapsible sidebar and all 4 Chart.js canvases
    res_dash = admin_client.get("/admin/dashboard")
    assert res_dash.status_code == 200
    dash_html = res_dash.data.decode("utf-8")
    assert "adminSidebar" in dash_html
    assert "chartCityStations" in dash_html
    assert "chartMonthlyBookings" in dash_html
    assert "chartConnectorMix" in dash_html
    assert "chartPaymentStatus" in dash_html


def test_razorpay_sqlite_fallback_and_decimal_safety(app):
    """
    Verify Razorpay order creation, Dynamic Payment QR generation, and settlement
    work without any decimal.Decimal parameter binding or interface errors when
    running on SQLite fallback (serverless/replica runtime).
    """
    import app.db as db
    from app.services.razorpay_service import (
        compute_tax_breakdown,
        create_razorpay_order,
        create_dynamic_payment_qr,
        generate_sandbox_payment_proof,
        verify_and_settle_razorpay_payment,
    )

    # 1. compute_tax_breakdown returns JSON-serializable floats, no raw Decimals
    breakdown = compute_tax_breakdown(436.60)
    assert isinstance(breakdown["base_amount"], float)
    assert isinstance(breakdown["tax_amount"], float)
    assert isinstance(breakdown["total_amount"], float)
    assert isinstance(breakdown["amount_paise"], int)
    assert breakdown["total_amount"] == 436.60

    # 2. Force SQLite mode to simulate serverless or standalone replica
    orig_state = db._MYSQL_UNAVAILABLE
    db._MYSQL_UNAVAILABLE = True
    try:
        with app.app_context():
            # Create a test booking reservation in SQLite
            db.execute(
                "INSERT INTO Bookings (booking_id, user_id, vehicle_id, point_id, start_at, end_at, estimated_energy_kwh, estimated_cost, booking_status) "
                "VALUES (999503, 2, 1, 1, '2026-11-25 18:00:00', '2026-11-25 19:00:00', 20.0, 436.60, 'PENDING')"
            )

            # Create Razorpay order - must not crash with Decimal binding error
            order, err = create_razorpay_order(booking_id=999503, user_id=2)
            assert err is None, f"Order creation failed: {err}"
            assert order is not None
            assert order["order_id"].startswith("order_sim_")
            assert order["amount_inr"] == 436.60

            # Create Dynamic Payment QR - must generate valid data URI
            qr_res, qr_err = create_dynamic_payment_qr(booking_id=999503, user_id=2)
            assert qr_err is None, f"QR generation failed: {qr_err}"
            assert qr_res is not None
            assert qr_res["qr_image_data_uri"].startswith("data:image/png;base64,")

            # Complete settlement in sandbox
            pay_id, sig = generate_sandbox_payment_proof(order["order_id"])
            settled, s_err = verify_and_settle_razorpay_payment(
                booking_id=999503,
                user_id=2,
                razorpay_order_id=order["order_id"],
                razorpay_payment_id=pay_id,
                razorpay_signature=sig,
            )
            assert s_err is None, f"Settlement failed: {s_err}"
            assert settled["payment_status"] == "SUCCESS"

            # Verify booking status changed to CONFIRMED
            b_row = db.query_one("SELECT booking_status FROM Bookings WHERE booking_id = 999503")
            assert b_row["booking_status"] == "CONFIRMED"
    finally:
        db.execute("DELETE FROM Payments WHERE booking_id = 999503")
        db.execute("DELETE FROM Bookings WHERE booking_id = 999503")
        db._MYSQL_UNAVAILABLE = orig_state
