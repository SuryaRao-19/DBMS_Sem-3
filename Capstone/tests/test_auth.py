"""
Authentication & Authorization Tests
EV Charging Station Management System - DBMS Capstone Project
"""
import pytest
from app.services.auth_service import authenticate_user, register_user
from app.db import execute


def test_valid_admin_login():
    """Verify administrator authentication with correct credentials."""
    user, err = authenticate_user("admin@evdemo.com", "Admin@123")
    assert err is None
    assert user is not None
    assert user["role"] == "ADMIN"
    assert user["account_status"] == "ACTIVE"


def test_valid_owner_login():
    """Verify EV customer driver and station partner authentication with correct credentials."""
    user, err = authenticate_user("aarav@example.com", "Owner@123")
    assert err is None
    assert user is not None
    assert user["role"] == "CUSTOMER"

    # Also verify station partner (OWNER) login
    partner, p_err = authenticate_user("owner.station01@example.test", "Partner@123")
    assert p_err is None
    assert partner is not None
    assert partner["role"] == "OWNER"


def test_invalid_password_rejection():
    """Verify authentication fails when providing an incorrect password."""
    user, err = authenticate_user("admin@evdemo.com", "WrongPassword!999")
    assert user is None
    assert "Invalid email or password" in err


def test_nonexistent_email_rejection():
    """Verify authentication fails for non-existent email addresses."""
    user, err = authenticate_user("unknown_user_9999@notfound.com", "Password@123")
    assert user is None
    assert "No account found" in err


def test_user_registration_and_login():
    """Verify registration creates user with secure hashed password and allows login."""
    test_email = "test_driver_new@evdemo.com"
    # Cleanup previous test run if present
    execute("DELETE FROM Users WHERE email = %s", (test_email,))

    uid, err = register_user("Test New Driver", test_email, "9876543210", "SecurePass@2026", "CUSTOMER")
    assert err is None
    assert uid is not None

    # Verify user can log in with clear password
    user, auth_err = authenticate_user(test_email, "SecurePass@2026")
    assert auth_err is None
    assert user["user_id"] == uid
    assert user["role"] == "CUSTOMER"

    # Clean up
    execute("DELETE FROM Users WHERE user_id = %s", (uid,))


def test_duplicate_email_registration_rejection():
    """Verify registration rejects duplicate email addresses."""
    uid, err = register_user("Duplicate User", "admin@evdemo.com", "9000000001", "Admin@123")
    assert uid is None
    assert "already exists" in err
