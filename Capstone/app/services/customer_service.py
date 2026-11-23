"""
Customer Mobility Service
EV Charging Station Management System - Production Hardened
"""
import io
import csv
from datetime import datetime
from app.db import query_all, query_one, execute, transaction


def get_customer_dashboard_kpis(user_id):
    """
    Retrieve authoritative real-time KPIs strictly scoped to the authenticated customer.
    No hardcoded statistics or cross-tenant leakage.
    """
    kpis = {
        "total_sessions": 0,
        "total_energy_kwh": 0.0,
        "total_amount_spent": 0.0,
        "active_bookings_count": 0,
        "vehicles_count": 0,
        "saved_stations_count": 0,
        "unread_notifications_count": 0,
    }

    try:
        # Session stats
        session_row = query_one(
            "SELECT COUNT(*) AS total_sessions, "
            "       COALESCE(SUM(energy_kwh), 0) AS total_kwh, "
            "       COALESCE(SUM(total_cost), 0) AS total_cost "
            "FROM ChargingSessions "
            "WHERE user_id = %s",
            (user_id,)
        )
        if session_row:
            kpis["total_sessions"] = int(session_row.get("total_sessions") or 0)
            kpis["total_energy_kwh"] = round(float(session_row.get("total_kwh") or 0.0), 2)
            kpis["total_amount_spent"] = round(float(session_row.get("total_cost") or 0.0), 2)

        # Active/upcoming bookings
        active_b = query_one(
            "SELECT COUNT(*) AS cnt FROM Bookings "
            "WHERE user_id = %s AND booking_status IN ('CONFIRMED', 'PENDING') AND end_at >= NOW()",
            (user_id,)
        )
        if active_b:
            kpis["active_bookings_count"] = int(active_b.get("cnt") or 0)

        # Vehicles count
        veh_row = query_one("SELECT COUNT(*) AS cnt FROM Vehicles WHERE user_id = %s", (user_id,))
        if veh_row:
            kpis["vehicles_count"] = int(veh_row.get("cnt") or 0)

        # Saved stations count
        saved_row = query_one("SELECT COUNT(*) AS cnt FROM SavedStations WHERE user_id = %s", (user_id,))
        if saved_row:
            kpis["saved_stations_count"] = int(saved_row.get("cnt") or 0)

        # Unread notifications count
        notif_row = query_one("SELECT COUNT(*) AS cnt FROM Notifications WHERE user_id = %s AND is_read = 0", (user_id,))
        if notif_row:
            kpis["unread_notifications_count"] = int(notif_row.get("cnt") or 0)
    except Exception:
        pass

    return kpis


def get_customer_recent_activity(user_id, limit=5):
    """Retrieve recent bookings and sessions for customer dashboard display."""
    try:
        recent_bookings = query_all(
            "SELECT b.*, s.station_name, s.city, cp.point_code, cp.connector_type, v.registration_no, "
            "       bq.qr_token "
            "FROM Bookings b "
            "JOIN ChargingPoints cp ON cp.point_id = b.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "JOIN Vehicles v ON v.vehicle_id = b.vehicle_id "
            "LEFT JOIN BookingQRCodes bq ON bq.booking_id = b.booking_id "
            "WHERE b.user_id = %s "
            "ORDER BY b.start_at DESC LIMIT %s",
            (user_id, limit)
        )

        recent_sessions = query_all(
            "SELECT cs.*, s.station_name, s.city, cp.point_code, cp.connector_type, v.registration_no, "
            "       p.payment_status, p.payment_id "
            "FROM ChargingSessions cs "
            "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
            "LEFT JOIN Payments p ON p.session_id = cs.session_id "
            "WHERE cs.user_id = %s "
            "ORDER BY cs.start_at DESC LIMIT %s",
            (user_id, limit)
        )
        return recent_bookings, recent_sessions
    except Exception:
        return [], []


# ============================================================================
# SAVED STATIONS
# ============================================================================

def is_station_saved(user_id, station_id):
    """Check if customer has bookmarked a station."""
    try:
        row = query_one(
            "SELECT saved_id FROM SavedStations WHERE user_id = %s AND station_id = %s",
            (user_id, station_id)
        )
        return bool(row)
    except Exception:
        return False


def toggle_saved_station(user_id, station_id, notes=None):
    """Bookmark or unbookmark a station for customer quick access."""
    existing = query_one(
        "SELECT saved_id FROM SavedStations WHERE user_id = %s AND station_id = %s",
        (user_id, station_id)
    )
    if existing:
        execute("DELETE FROM SavedStations WHERE saved_id = %s", (existing["saved_id"],))
        return False, "Station removed from your saved stations."

    # Validate station exists
    st = query_one("SELECT station_name FROM Stations WHERE station_id = %s", (station_id,))
    if not st:
        return False, "Station not found."

    execute(
        "INSERT INTO SavedStations (user_id, station_id) VALUES (%s, %s)",
        (user_id, station_id)
    )
    return True, f"'{st['station_name']}' saved to your favorites!"


def get_saved_stations_for_user(user_id):
    """Retrieve full station cards bookmarked by customer."""
    try:
        return query_all(
            "SELECT ss.saved_id, ss.created_at AS saved_at, "
            "       s.*, "
            "       COUNT(DISTINCT cp.point_id) AS total_points, "
            "       SUM(CASE WHEN cp.point_status = 'AVAILABLE' THEN 1 ELSE 0 END) AS available_points, "
            "       MIN(cp.tariff_per_kwh) AS min_tariff, "
            "       MAX(cp.max_power_kw) AS max_power "
            "FROM SavedStations ss "
            "JOIN Stations s ON s.station_id = ss.station_id "
            "LEFT JOIN ChargingPoints cp ON cp.station_id = s.station_id "
            "WHERE ss.user_id = %s "
            "GROUP BY ss.saved_id, s.station_id "
            "ORDER BY ss.created_at DESC",
            (user_id,)
        )
    except Exception:
        return []


# ============================================================================
# NOTIFICATIONS
# ============================================================================

def add_notification(user_id, title, message, category="SYSTEM", link_url=None):
    """Queue an in-app notification for a customer."""
    if not user_id or not title:
        return None
    nid = execute(
        "INSERT INTO Notifications (user_id, title, message, category, link_url, is_read) "
        "VALUES (%s, %s, %s, %s, %s, 0)",
        (user_id, title.strip()[:120], (message or "").strip(), (category or "SYSTEM")[:50], (link_url or "").strip()[:255] or None)
    )
    return nid


def get_customer_notifications(user_id, limit=50):
    """Retrieve in-app notifications for customer."""
    return query_all(
        "SELECT * FROM Notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit)
    )


def mark_notification_read(notification_id, user_id):
    """Mark a specific notification as read ensuring customer ownership."""
    execute(
        "UPDATE Notifications SET is_read = 1 WHERE notification_id = %s AND user_id = %s",
        (notification_id, user_id)
    )
    return True


def mark_all_notifications_read(user_id):
    """Mark all notifications for customer as read."""
    execute("UPDATE Notifications SET is_read = 1 WHERE user_id = %s", (user_id,))
    return True


# ============================================================================
# CHARGING HISTORY & CSV EXPORT
# ============================================================================

def get_customer_charging_history(user_id, start_date=None, end_date=None, search=None, sort="desc", page=1, per_page=10):
    """
    Retrieve paginated, filterable, sortable charging sessions history for customer.
    Returns (sessions_list, total_count, total_pages, current_page).
    """
    sql = (
        "FROM ChargingSessions cs "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "LEFT JOIN Payments p ON p.session_id = cs.session_id "
        "WHERE cs.user_id = %s "
    )
    params = [user_id]

    if start_date:
        sql += " AND cs.start_at >= %s"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        sql += " AND cs.start_at <= %s"
        params.append(f"{end_date} 23:59:59")
    if search and search.strip():
        like = f"%{search.strip()}%"
        sql += " AND (s.station_name LIKE %s OR s.city LIKE %s OR v.registration_no LIKE %s OR cp.point_code LIKE %s)"
        params.extend([like, like, like, like])

    count_row = query_one("SELECT COUNT(*) AS total " + sql, params)
    total_count = int(count_row.get("total") or 0) if count_row else 0

    order_dir = "ASC" if str(sort).lower() == "asc" else "DESC"
    offset = max(0, (page - 1) * per_page)

    select_sql = (
        "SELECT cs.*, s.station_name, s.city, s.address, cp.point_code, cp.connector_type, "
        "       v.registration_no, v.make, v.model, p.payment_status, p.payment_id, "
        "       p.transaction_reference, p.payment_method "
        + sql +
        f" ORDER BY cs.start_at {order_dir} LIMIT %s OFFSET %s"
    )
    exec_params = list(params)
    exec_params.extend([per_page, offset])
    rows = query_all(select_sql, exec_params)

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return rows, total_count, total_pages, page


def generate_customer_history_csv(user_id, start_date=None, end_date=None, search=None):
    """Generate RFC 4180 CSV export of customer's charging sessions."""
    rows, _, _, _ = get_customer_charging_history(
        user_id, start_date=start_date, end_date=end_date, search=search, sort="desc", page=1, per_page=10000
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Session ID",
        "Date & Time",
        "Station Name",
        "City",
        "Charging Point",
        "Connector",
        "Vehicle",
        "Energy (kWh)",
        "Rate (INR/kWh)",
        "Total Cost (INR)",
        "Session Status",
        "Payment Status",
        "Reference",
    ])

    for r in rows:
        writer.writerow([
            r["session_id"],
            str(r.get("start_at") or ""),
            r.get("station_name") or "",
            r.get("city") or "",
            r.get("point_code") or "",
            r.get("connector_type") or "",
            f"{r.get('make', '')} {r.get('model', '')} ({r.get('registration_no', '')})".strip(),
            f"{float(r.get('energy_kwh') or 0.0):.2f}",
            f"{float(r.get('tariff_per_kwh') or 0.0):.2f}",
            f"{float(r.get('total_cost') or 0.0):.2f}",
            r.get("session_status") or "",
            r.get("payment_status") or "PENDING",
            r.get("transaction_reference") or "",
        ])

    return output.getvalue()


# ============================================================================
# PAYMENTS & TRANSACTIONS
# ============================================================================

def get_customer_payments(user_id, search=None, status=None, start_date=None, end_date=None, page=1, per_page=15, limit=None):
    """Retrieve filtered, paginated payment transactions history for authenticated customer."""
    if limit is not None and (search is None and status is None and start_date is None and end_date is None):
        per_page = int(limit)

    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(100, int(per_page)))
    except (ValueError, TypeError):
        per_page = 15
    offset = (page - 1) * per_page

    where_clauses = ["(cs.user_id = %s OR b.user_id = %s)"]
    params = [user_id, user_id]

    if status and str(status).strip() and str(status).strip().upper() != "ALL":
        where_clauses.append("p.payment_status = %s")
        params.append(str(status).strip().upper())

    if start_date and str(start_date).strip():
        where_clauses.append("p.created_at >= %s")
        params.append(f"{str(start_date).strip()} 00:00:00")

    if end_date and str(end_date).strip():
        where_clauses.append("p.created_at <= %s")
        params.append(f"{str(end_date).strip()} 23:59:59")

    if search and str(search).strip():
        term = f"%{str(search).strip()}%"
        where_clauses.append(
            "(p.transaction_reference LIKE %s OR p.razorpay_order_id LIKE %s OR "
            " s.station_name LIKE %s OR s2.station_name LIKE %s OR "
            " v.registration_no LIKE %s OR v2.registration_no LIKE %s)"
        )
        params.extend([term, term, term, term, term, term])

    where_sql = " AND ".join(where_clauses)

    count_sql = (
        "SELECT COUNT(*) AS cnt "
        "FROM Payments p "
        "LEFT JOIN ChargingSessions cs ON cs.session_id = p.session_id "
        "LEFT JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "LEFT JOIN Stations s ON s.station_id = cp.station_id "
        "LEFT JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "LEFT JOIN Bookings b ON b.booking_id = p.booking_id "
        "LEFT JOIN ChargingPoints cp2 ON cp2.point_id = b.point_id "
        "LEFT JOIN Stations s2 ON s2.station_id = cp2.station_id "
        "LEFT JOIN Vehicles v2 ON v2.vehicle_id = b.vehicle_id "
        f"WHERE {where_sql}"
    )
    count_row = query_one(count_sql, list(params))
    total_count = int(count_row.get("cnt") or 0) if count_row else 0

    select_sql = (
        "SELECT p.*, "
        "       COALESCE(cs.energy_kwh, 0) AS energy_kwh, "
        "       COALESCE(cs.start_at, p.created_at) AS start_at, "
        "       COALESCE(cs.end_at, p.paid_at) AS end_at, "
        "       COALESCE(s.station_name, s2.station_name, 'EZ Charge Hub') AS station_name, "
        "       COALESCE(s.city, s2.city, '') AS city, "
        "       COALESCE(s.address, s2.address, '') AS address, "
        "       COALESCE(cp.point_code, cp2.point_code, 'CP-01') AS point_code, "
        "       COALESCE(cp.connector_type, cp2.connector_type, 'CCS2') AS connector_type, "
        "       COALESCE(v.registration_no, v2.registration_no, 'EV-VEHICLE') AS registration_no, "
        "       COALESCE(v.make, v2.make, '') AS make, "
        "       COALESCE(v.model, v2.model, '') AS model "
        "FROM Payments p "
        "LEFT JOIN ChargingSessions cs ON cs.session_id = p.session_id "
        "LEFT JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "LEFT JOIN Stations s ON s.station_id = cp.station_id "
        "LEFT JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "LEFT JOIN Bookings b ON b.booking_id = p.booking_id "
        "LEFT JOIN ChargingPoints cp2 ON cp2.point_id = b.point_id "
        "LEFT JOIN Stations s2 ON s2.station_id = cp2.station_id "
        "LEFT JOIN Vehicles v2 ON v2.vehicle_id = b.vehicle_id "
        f"WHERE {where_sql} "
        "ORDER BY p.created_at DESC LIMIT %s OFFSET %s"
    )
    exec_params = list(params) + [per_page, offset]
    rows = query_all(select_sql, exec_params)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return rows, total_count, total_pages, page


def get_customer_payment_summary(user_id):
    """Compute summary card totals strictly for authenticated customer."""
    row = query_one(
        "SELECT COUNT(*) AS total_tx, "
        "       COALESCE(SUM(CASE WHEN p.payment_status IN ('SUCCESS', 'PAID', 'CAPTURED') THEN p.amount ELSE 0 END), 0) AS total_paid, "
        "       COALESCE(SUM(CASE WHEN p.payment_status = 'PENDING' THEN p.amount ELSE 0 END), 0) AS total_pending, "
        "       COUNT(CASE WHEN p.payment_status IN ('SUCCESS', 'PAID', 'CAPTURED') THEN 1 END) AS paid_count, "
        "       COUNT(CASE WHEN p.payment_status = 'PENDING' THEN 1 END) AS pending_count "
        "FROM Payments p "
        "LEFT JOIN ChargingSessions cs ON cs.session_id = p.session_id "
        "LEFT JOIN Bookings b ON b.booking_id = p.booking_id "
        "WHERE (cs.user_id = %s OR b.user_id = %s)",
        (user_id, user_id)
    )
    return {
        "total_tx": int(row.get("total_tx") or 0) if row else 0,
        "total_paid": round(float(row.get("total_paid") or 0.0), 2) if row else 0.0,
        "total_pending": round(float(row.get("total_pending") or 0.0), 2) if row else 0.0,
        "paid_count": int(row.get("paid_count") or 0) if row else 0,
        "pending_count": int(row.get("pending_count") or 0) if row else 0,
    }
