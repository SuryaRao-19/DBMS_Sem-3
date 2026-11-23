"""
Phase 2 Security Remediation Regression & Hardening Tests
EV Charging Station Management System
"""
import re
import pytest
from app import create_app
from app.db import execute, query_one
from app.services.auth_service import register_user, authenticate_user
from app.services.session_service import start_session, complete_session


def _extract_csrf(html_bytes):
    html = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if m:
        return m.group(1)
    m2 = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
    return m2.group(1) if m2 else None


def test_public_registration_blocks_admin_escalation(client):
    """Public registration must reject role=ADMIN and never create an ADMIN user."""
    email = "attacker_admin@example.com"
    execute("DELETE FROM Users WHERE email = %s", (email,))

    res = client.post("/register", data={
        "full_name": "Attacker",
        "email": email,
        "phone": "9999999999",
        "password": "Password@123",
        "confirm_password": "Password@123",
        "role": "ADMIN",
    })
    assert res.status_code == 403
    created = query_one("SELECT user_id, role FROM Users WHERE email = %s", (email,))
    assert created is None

    # Service-level check: direct call without allow_admin=True must reject ADMIN
    uid, err = register_user("Attacker", email, "9999999999", "Password@123", role="ADMIN")
    assert uid is None
    assert "cannot be created via public registration" in err


def test_register_page_has_no_admin_role_option(client):
    """Public registration HTML must not expose an ADMIN role selector."""
    res = client.get("/register")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert 'value="ADMIN"' not in html


def test_login_page_has_no_demo_credentials(client):
    """Login page must not embed admin/owner demo passwords."""
    res = client.get("/login")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Admin@123" not in html
    assert "Owner@123" not in html
    assert "fillDemo" not in html


def test_admin_can_provision_admin_user_but_owner_cannot(admin_client, owner_client):
    """Only authenticated ADMIN can create ADMIN accounts via /admin/users/create."""
    email = "provisioned_admin@example.com"
    execute("DELETE FROM AuditLogs WHERE details LIKE %s", (f"%{email}%",))
    execute("DELETE FROM Users WHERE email = %s", (email,))

    # Owner blocked (403)
    res_owner = owner_client.post("/admin/users/create", data={
        "full_name": "Unauthorized Admin",
        "email": email,
        "phone": "9111111111",
        "password": "Password@123",
        "role": "ADMIN",
    })
    assert res_owner.status_code == 403
    assert query_one("SELECT user_id FROM Users WHERE email = %s", (email,)) is None

    # Admin succeeds
    res_admin = admin_client.post("/admin/users/create", data={
        "full_name": "Provisioned Admin",
        "email": email,
        "phone": "9222222222",
        "password": "Password@123",
        "role": "ADMIN",
    }, follow_redirects=True)
    assert res_admin.status_code == 200
    user = query_one("SELECT user_id, role FROM Users WHERE email = %s", (email,))
    assert user is not None
    assert user["role"] == "ADMIN"

    # Cleanup
    execute("DELETE FROM AuditLogs WHERE entity_name = 'Users' AND entity_id = %s", (user["user_id"],))
    execute("DELETE FROM Users WHERE user_id = %s", (user["user_id"],))


def test_idor_payment_blocked_cross_user(owner_client, other_owner_client):
    """User 3 (Priya) cannot settle or pay User 2 (Aarav)'s completed session."""
    # Create a completed unpaid session for User 2
    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = 1")
    execute("DELETE FROM ChargingSessions WHERE user_id = 2 AND session_status = 'IN_PROGRESS'")
    sid, err = start_session(user_id=2, vehicle_id=1, point_id=1)
    assert err is None
    completed, err2 = complete_session(sid, 12.5, user_id=2)
    assert err2 is None

    # User 3 attempts API payment -> 403
    res_api = other_owner_client.post("/api/session/pay", json={"session_id": sid, "payment_method": "UPI"})
    assert res_api.status_code == 403
    assert res_api.get_json()["success"] is False

    # User 3 attempts form payment -> 403
    res_form = other_owner_client.post("/owner/charging", data={
        "action": "pay",
        "session_id": sid,
        "payment_method": "UPI",
    })
    assert res_form.status_code == 403

    # Nonexistent session -> 404
    res_404 = owner_client.post("/api/session/pay", json={"session_id": 999999, "payment_method": "UPI"})
    assert res_404.status_code == 404

    # Real owner succeeds
    res_ok = owner_client.post("/api/session/pay", json={"session_id": sid, "payment_method": "UPI"})
    assert res_ok.status_code == 200
    payload = res_ok.get_json()
    assert payload["success"] is True
    assert float(payload["amount"]) == float(completed["total_cost"])

    # Cleanup
    execute("DELETE FROM Payments WHERE session_id = %s", (sid,))
    execute("DELETE FROM ChargingSessions WHERE session_id = %s", (sid,))


def test_idor_start_session_with_other_user_booking_blocked(other_owner_client):
    """User 3 cannot start a charging session referencing User 2's booking_id."""
    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = 1")
    execute("DELETE FROM ChargingSessions WHERE user_id = 3 AND session_status = 'IN_PROGRESS'")

    # Booking 7 belongs to user 8 (Arjun) on point 1
    res = other_owner_client.post("/owner/charging", data={
        "action": "start",
        "vehicle_id": 2,
        "point_id": 1,
        "booking_id": 7,
    })
    assert res.status_code == 403


def test_csrf_protection_enforced(csrf_client):
    """Missing or invalid CSRF tokens must be rejected with HTTP 400; valid tokens succeed."""
    # Missing CSRF token on login POST -> 400
    res_missing = csrf_client.post("/login", data={"email": "aarav@example.com", "password": "Owner@123"})
    assert res_missing.status_code == 400

    # Invalid CSRF token on login POST -> 400
    res_invalid = csrf_client.post("/login", data={
        "csrf_token": "invalid-csrf-token",
        "email": "aarav@example.com",
        "password": "Owner@123",
    })
    assert res_invalid.status_code == 400

    # Valid CSRF token from GET /login -> 200 after redirect to dashboard
    get_res = csrf_client.get("/login")
    token = _extract_csrf(get_res.data)
    assert token is not None

    res_ok = csrf_client.post("/login", data={
        "csrf_token": token,
        "email": "aarav@example.com",
        "password": "Owner@123",
    }, follow_redirects=False)
    assert res_ok.status_code == 302
    assert "/customer/dashboard" in res_ok.location or "/owner/dashboard" in res_ok.location

    # JSON API POST without X-CSRFToken -> 400 JSON
    res_api_no_csrf = csrf_client.post("/api/session/pay", json={"session_id": 1})
    assert res_api_no_csrf.status_code == 400
    assert res_api_no_csrf.get_json()["success"] is False


def test_inactive_user_session_revoked_immediately(app):
    """Deactivating a user immediately blocks their existing session on pages and APIs."""
    # Use seeded user 4 (Rohan Gupta)
    orig = query_one("SELECT account_status FROM Users WHERE user_id = 4")["account_status"]
    try:
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = 4
            sess["role"] = "OWNER"
            sess["full_name"] = "Rohan Gupta"

        # Active user can access dashboard & API
        assert client.get("/owner/dashboard").status_code == 200
        assert client.get("/api/points/status").status_code == 200

        # Admin deactivates user 4 in DB
        execute("UPDATE Users SET account_status = 'INACTIVE' WHERE user_id = 4")

        # Existing session is immediately invalidated
        res_page = client.get("/owner/dashboard", follow_redirects=False)
        assert res_page.status_code == 302
        assert "/login" in res_page.location

        # API also returns 401 when session is re-populated or active
        with client.session_transaction() as sess:
            sess["user_id"] = 4
            sess["role"] = "OWNER"
        res_api = client.get("/api/points/status")
        assert res_api.status_code == 401
    finally:
        execute("UPDATE Users SET account_status = %s WHERE user_id = 4", (orig,))


def test_sql_injection_on_login_and_search(client):
    """Parameterized queries must safely reject SQL injection payloads."""
    user, err = authenticate_user("' OR '1'='1", "anything")
    assert user is None
    assert err is not None

    res = client.get("/stations?q=' OR 1=1 --")
    assert res.status_code == 200


def test_production_config_requires_secret_key(monkeypatch):
    """Production mode must fail safely when SECRET_KEY is not configured."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_session_cookie_security_flags(app):
    """Verify secure session cookie attributes."""
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

