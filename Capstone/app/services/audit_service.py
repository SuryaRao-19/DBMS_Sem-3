"""
Audit and System Settings Service
EV Charging Station Management System - Major Upgrade 2.0
"""
from app.db import query_all, query_one, execute


def log_audit_event(action, entity_name, entity_id=None, user_id=None, details=None, ip_address=None):
    """
    Record an administrative or critical operational audit log entry.
    """
    sql = """
        INSERT INTO AuditLogs (user_id, action, entity_name, entity_id, details, ip_address)
        VALUES (%s, %s, %s, %s, %s, %s);
    """
    try:
        return execute(sql, (user_id, action, entity_name, entity_id, str(details) if details else None, ip_address))
    except Exception as e:
        # Fallback print so an audit failure does not crash the host transaction if not desired
        print(f"[AUDIT WARNING] Failed to record audit log: {e}")
        return None


def get_audit_logs(limit=50, entity_name=None):
    """
    Retrieve recent audit logs with user attribution.
    """
    if entity_name:
        sql = """
            SELECT a.*, u.full_name as user_name, u.email as user_email
            FROM AuditLogs a
            LEFT JOIN Users u ON a.user_id = u.user_id
            WHERE a.entity_name = %s
            ORDER BY a.created_at DESC
            LIMIT %s;
        """
        return query_all(sql, (entity_name, limit))
    else:
        sql = """
            SELECT a.*, u.full_name as user_name, u.email as user_email
            FROM AuditLogs a
            LEFT JOIN Users u ON a.user_id = u.user_id
            ORDER BY a.created_at DESC
            LIMIT %s;
        """
        return query_all(sql, (limit,))


def get_system_settings():
    """
    Retrieve all system settings as a dictionary.
    """
    rows = query_all("SELECT setting_key, setting_value, description, updated_at FROM SystemSettings ORDER BY setting_key;")
    return {r["setting_key"]: r["setting_value"] for r in rows}


def get_system_settings_list():
    """
    Retrieve all system settings as a list of dicts.
    """
    return query_all("SELECT setting_key, setting_value, description, updated_at FROM SystemSettings ORDER BY setting_key;")


def get_setting(key, default=None):
    """
    Retrieve a single setting value by key.
    """
    row = query_one("SELECT setting_value FROM SystemSettings WHERE setting_key = %s;", (key,))
    return row["setting_value"] if row else default


def update_system_setting(key, value, user_id=None):
    """
    Update a setting value and record an audit log entry.
    """
    old_row = query_one("SELECT setting_value FROM SystemSettings WHERE setting_key = %s;", (key,))
    if not old_row:
        return False, "Setting key not found"

    sql = "UPDATE SystemSettings SET setting_value = %s WHERE setting_key = %s;"
    execute(sql, (str(value), key))

    # Audit the change
    log_audit_event(
        action="UPDATE_SETTING",
        entity_name="SystemSettings",
        entity_id=None,
        user_id=user_id,
        details=f"Updated '{key}' from '{old_row['setting_value']}' to '{value}'"
    )
    return True, "Setting updated successfully"
