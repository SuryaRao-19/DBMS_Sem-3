"""
Phase 2-8 Regression Tests: Google OAuth 2.0 / OIDC, Forgot/Reset Password,
CSRF Recovery, Unified Dark EV Theme & Zero-Flicker Sidebar Architecture.
EV Charging Station Management System
"""
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from app import create_app
from app.db import execute, query_one
from app.services.auth_service import (
    authenticate_user,
    register_user,
    authenticate_or_register_google_user,
    create_password_reset_token,
    reset_password_with_token,
)


def _cleanup_user_by_email(email):
    row = query_one("SELECT user_id FROM Users WHERE email = %s", (email,))
    if row:
        uid = row["user_id"]
        execute("DELETE FROM PasswordResetTokens WHERE user_id = %s", (uid,))
        execute("DELETE FROM AuditLogs WHERE user_id = %s OR (entity_name = 'Users' AND entity_id = %s)", (uid, uid))
        execute("DELETE FROM Users WHERE user_id = %s", (uid,))


def test_google_oauth_unconfigured_graceful_fallback(client, monkeypatch):
    """When GOOGLE_CLIENT_ID/SECRET are unset, /auth/google/login redirects safely with setup notice."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    test_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test_secret_unconfigured_oauth",
        "WTF_CSRF_ENABLED": False,
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
    })
    c = test_app.test_client()
    res = c.get("/auth/google/login", follow_redirects=True)
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Google Sign-In is not configured yet" in html
    assert "Continue with Google" in html


def test_google_oauth_login_and_callback_lifecycle(monkeypatch):
    """
    Validate full mocked Google OIDC flow:
    1) /auth/google/login generates nonce & delegates to Authlib authorize_redirect
    2) /auth/google/callback rejects unverified emails
    3) /auth/google/callback creates new Google user strictly as OWNER (never ADMIN)
    4) /auth/google/callback rejects OAuth state/token exception safely
    5) Returning Google user signs into existing account without duplicating row
    """
    test_email = "oauth_driver_test@example.com"
    test_sub = "google-sub-test-991001"
    _cleanup_user_by_email(test_email)

    try:
        test_app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test_secret_configured_oauth",
            "WTF_CSRF_ENABLED": False,
            "GOOGLE_CLIENT_ID": "test-google-client-id.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
            "GOOGLE_REDIRECT_URI": "http://127.0.0.1:5000/auth/google/callback",
        })

        mock_google = MagicMock()
        mock_google.client_id = "test-google-client-id.apps.googleusercontent.com"
        mock_google.authorize_redirect.return_value = test_app.response_class(
            status=302,
            headers={"Location": "https://accounts.google.com/o/oauth2/v2/auth?state=abc"},
        )
        monkeypatch.setattr("app.routes.auth.ensure_google_oauth_client", lambda _app: mock_google)

        c = test_app.test_client()
        login_res = c.get("/auth/google/login", follow_redirects=False)
        assert login_res.status_code == 302
        assert "accounts.google.com" in login_res.location
        assert mock_google.authorize_redirect.called
        with c.session_transaction() as sess:
            assert sess.get("google_oauth_nonce")

        # Callback with unverified email -> rejected cleanly
        mock_google.authorize_access_token.return_value = {
            "userinfo": {
                "sub": test_sub,
                "email": test_email,
                "email_verified": False,
                "name": "Unverified OAuth User",
            }
        }
        res_unverified = c.get("/auth/google/callback", follow_redirects=True)
        assert res_unverified.status_code == 200
        assert "not verified" in res_unverified.data.decode("utf-8")
        assert query_one("SELECT user_id FROM Users WHERE email = %s", (test_email,)) is None

        # Callback with verified email -> creates CUSTOMER user & signs into customer dashboard
        mock_google.authorize_access_token.return_value = {
            "userinfo": {
                "sub": test_sub,
                "email": test_email,
                "email_verified": True,
                "name": "OAuth Driver",
                "picture": "https://lh3.googleusercontent.com/test-avatar",
            }
        }
        res_ok = c.get("/auth/google/callback", follow_redirects=False)
        assert res_ok.status_code == 302
        assert "/customer/dashboard" in res_ok.location or "/owner/dashboard" in res_ok.location

        db_user = query_one(
            "SELECT user_id, role, auth_provider, email_verified, password_hash, google_sub, last_login "
            "FROM Users WHERE email = %s",
            (test_email,),
        )
        assert db_user is not None
        assert db_user["role"] == "CUSTOMER"
        assert db_user["role"] != "ADMIN"
        assert db_user["auth_provider"] == "GOOGLE"
        assert db_user["email_verified"] == 1
        assert db_user["password_hash"] is None
        assert db_user["google_sub"] == test_sub
        assert db_user["last_login"] is not None

        # Password login attempt on Google-only account gives helpful message (no crash)
        _, pw_err = authenticate_user(test_email, "anything123")
        assert "Google Sign-In" in pw_err

        # Logout & invalid OAuth state failure handled gracefully
        c.get("/logout")
        mock_google.authorize_access_token.side_effect = RuntimeError("mismatching_state")
        res_err = c.get("/auth/google/callback", follow_redirects=True)
        assert res_err.status_code == 200
        assert "verification failed" in res_err.data.decode("utf-8")

        # Returning login matches existing user without creating duplicate
        mock_google.authorize_access_token.side_effect = None
        res_return = c.get("/auth/google/callback", follow_redirects=False)
        assert res_return.status_code == 302
        assert "/customer/dashboard" in res_return.location or "/owner/dashboard" in res_return.location
        count_row = query_one("SELECT COUNT(*) AS cnt FROM Users WHERE email = %s", (test_email,))
        assert count_row["cnt"] == 1
    finally:
        _cleanup_user_by_email(test_email)


def test_google_oauth_blocks_blind_linking_unverified_local_account():
    """Never auto-link a Google OIDC login onto an unverified local password account."""
    email = "local_unverified_target@example.com"
    _cleanup_user_by_email(email)
    try:
        uid, err = register_user("Local Owner", email, "9988776655", "LocalPass@123", role="OWNER")
        assert uid is not None and err is None

        # Unverified local account -> auto-link refused
        user, link_err = authenticate_or_register_google_user(
            google_sub="google-sub-hijack-check",
            email=email,
            full_name="Local Owner",
            email_verified=True,
        )
        assert user is None
        assert "existing local password account" in link_err
    finally:
        _cleanup_user_by_email(email)


def test_forgot_and_reset_password_flow(client):
    """Forgot-password creates single-use SHA-256 token in MySQL and resets password cleanly."""
    email = "pw_reset_driver@example.com"
    _cleanup_user_by_email(email)
    try:
        uid, err = register_user("Reset User", email, "9123456789", "OldPass@123", role="OWNER")
        assert uid is not None and err is None

        res_req = client.post("/forgot-password", data={"email": email}, follow_redirects=True)
        assert res_req.status_code == 200
        assert "password reset link has been generated" in res_req.data.decode("utf-8")

        raw_token = create_password_reset_token(email)
        assert raw_token is not None

        res_get = client.get(f"/reset-password/{raw_token}")
        assert res_get.status_code == 200
        assert email in res_get.data.decode("utf-8")

        res_post = client.post(
            f"/reset-password/{raw_token}",
            data={"password": "NewStrongPass@123", "confirm_password": "NewStrongPass@123"},
            follow_redirects=False,
        )
        assert res_post.status_code == 302
        assert "/login" in res_post.location

        # New password works; old password fails; token replay rejected
        user, auth_err = authenticate_user(email, "NewStrongPass@123")
        assert user is not None and auth_err is None
        bad_user, _ = authenticate_user(email, "OldPass@123")
        assert bad_user is None
        ok_replay, _ = reset_password_with_token(raw_token, "AnotherPass@123")
        assert ok_replay is False
    finally:
        _cleanup_user_by_email(email)


def test_csrf_refresh_endpoint_cache_headers_and_recovery_ui(csrf_client):
    """Verify /auth/csrf-token refresh, no-store auth headers, and recovery guidance on 400 CSRFError."""
    res_login = csrf_client.get("/login")
    assert res_login.status_code == 200
    assert "no-store" in res_login.headers.get("Cache-Control", "")

    res_tok = csrf_client.get("/auth/csrf-token")
    assert res_tok.status_code == 200
    assert "no-store" in res_tok.headers.get("Cache-Control", "")
    payload = res_tok.get_json()
    assert payload and payload.get("csrf_token")

    # Missing CSRF renders helpful recovery UI while preserving 400 status
    res_bad = csrf_client.post("/login", data={"email": "aarav@example.com", "password": "Owner@123"})
    assert res_bad.status_code == 400
    html = res_bad.data.decode("utf-8")
    assert "Reload Fresh Form" in html


def test_unified_dark_theme_and_zero_flicker_sidebar_assets(client, admin_client):
    """
    Confirm unified Dark EV theme across public, auth, owner & admin views
    with zero Light Admin (#F4F7FA) overrides and pre-paint sidebar class init.
    """
    css = pathlib.Path("app/static/css/style.css").read_text(encoding="utf-8")
    assert "--color-background: #0B1220;" in css
    assert "--color-surface: #162338;" in css
    assert "--color-primary: #00D6A0;" in css
    assert "--color-accent: #00C8FF;" in css
    assert "background-color: #F4F7FA" not in css
    assert "html.sidebar-preload .admin-sidebar" in css
    assert "prefers-reduced-motion" in css

    base_html = pathlib.Path("app/templates/base.html").read_text(encoding="utf-8")
    assert "sidebar-is-collapsed" in base_html
    assert "sidebar-preload" in base_html

    res_admin = admin_client.get("/admin/dashboard")
    assert res_admin.status_code == 200
    admin_html = res_admin.data.decode("utf-8")
    assert "Chart.defaults.color = '#94A3B8'" in admin_html
    assert "Chart.defaults.color = '#475569'" not in admin_html

    res_login = client.get("/login")
    login_html = res_login.data.decode("utf-8")
    assert "Continue with Google" in login_html
    assert "Forgot password?" in login_html
    assert "togglePasswordVisibility" in login_html

