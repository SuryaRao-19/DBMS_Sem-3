"""
Tests for Audit Logs, System Settings, and Database Health Check
EV Charging Station Management System - Major Upgrade 2.0
"""
from app.services.audit_service import (
    log_audit_event, get_audit_logs, get_system_settings,
    get_setting, update_system_setting
)
from app.db import query_one


def test_api_health_endpoint(client):
    """Verify safe health check API endpoint."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "HEALTHY"
    assert data["database_connected"] is True
    assert data["database_name"] == "ev_charging_db"
    assert data["engine"] == "InnoDB"


def test_audit_log_service_event_recording():
    """Verify audit log creation and attribution."""
    log_id = log_audit_event(
        action="TEST_ACTION",
        entity_name="TestEntity",
        entity_id=999,
        user_id=1,
        details="Automated test audit log entry",
        ip_address="127.0.0.1"
    )
    assert log_id is not None

    logs = get_audit_logs(limit=10, entity_name="TestEntity")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["action"] == "TEST_ACTION"
    assert latest["entity_name"] == "TestEntity"
    assert latest["entity_id"] == 999
    assert latest["user_id"] == 1


def test_system_settings_retrieval_and_update():
    """Verify reading and updating system configuration settings."""
    settings = get_system_settings()
    assert "tax_rate_percent" in settings
    assert "app_currency" in settings

    # Update setting
    success, msg = update_system_setting("tax_rate_percent", "18.50", user_id=1)
    assert success is True
    assert get_setting("tax_rate_percent") == "18.50"

    # Restore setting
    update_system_setting("tax_rate_percent", "18.00", user_id=1)
    assert get_setting("tax_rate_percent") == "18.00"


def test_admin_audit_logs_page(admin_client):
    """Verify administrator audit trail and settings portal."""
    res = admin_client.get("/admin/audit-logs")
    assert res.status_code == 200
    assert b"Audit Trail &amp; System Configuration" in res.data or b"Audit Trail" in res.data
    assert b"System Configuration Parameters" in res.data
    assert b"tax_rate_percent" in res.data


def test_admin_setting_update_post(admin_client):
    """Verify updating a system setting via administrative form submission."""
    res = admin_client.post("/admin/settings/update", data={
        "setting_key": "cancellation_grace_mins",
        "setting_value": "20"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert get_setting("cancellation_grace_mins") == "20"

    # Revert to standard default
    admin_client.post("/admin/settings/update", data={
        "setting_key": "cancellation_grace_mins",
        "setting_value": "15"
    }, follow_redirects=True)
    assert get_setting("cancellation_grace_mins") == "15"
