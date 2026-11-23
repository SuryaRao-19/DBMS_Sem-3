"""
Pytest Test Fixtures and Configuration
EV Charging Station Management System - Production Hardened
"""
import pytest
from app import create_app
from app.db import get_db_connection


@pytest.fixture(scope="session")
def app():
    """Create Flask application configured for baseline test execution."""
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test_secret_key_dbms_capstone_2026",
        "WTF_CSRF_ENABLED": False,
    })
    return app


@pytest.fixture(scope="session")
def csrf_app():
    """Create Flask application with CSRF enforcement enabled."""
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test_csrf_secret_key_dbms_capstone_2026",
        "WTF_CSRF_ENABLED": True,
    })
    return app


@pytest.fixture
def client(app):
    """Anonymous HTTP test client."""
    return app.test_client()


@pytest.fixture
def csrf_client(csrf_app):
    """Anonymous HTTP test client with CSRF validation active."""
    return csrf_app.test_client()


@pytest.fixture
def admin_client(app):
    """Authenticated Admin test client."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["full_name"] = "System Admin"
        sess["email"] = "admin@evdemo.com"
        sess["role"] = "ADMIN"
    return client


@pytest.fixture
def owner_client(app):
    """Authenticated EV Owner test client (Aarav Sharma, user_id=2)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["full_name"] = "Aarav Sharma"
        sess["email"] = "aarav@example.com"
        sess["role"] = "OWNER"
    return client


@pytest.fixture
def other_owner_client(app):
    """Authenticated second EV Owner test client (Priya Verma, user_id=3)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["full_name"] = "Priya Verma"
        sess["email"] = "priya@example.com"
        sess["role"] = "OWNER"
    return client
