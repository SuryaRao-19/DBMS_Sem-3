"""
Station Partner (Owner) Service
EV Charging Station Management System - Production Hardened
"""
from datetime import datetime
from app.db import query_all, query_one, execute, transaction
from app.services.audit_service import log_audit_event
from app.services.customer_service import add_notification


def submit_owner_application(
    applicant_name,
    email,
    phone,
    company_name,
    station_name,
    city,
    state,
    pincode,
    proposed_chargers=1,
    power_capacity_kw=30.0,
    user_id=None,
):
    """
    Submit a new charging station partner application.
    Can be submitted by an authenticated customer or public prospective host.
    """
    if not applicant_name or not email or not station_name or not city:
        return None, "Name, email, station name, and city are required."

    email_clean = email.strip().lower()
    chargers = max(1, int(proposed_chargers or 1))
    power = max(3.3, float(power_capacity_kw or 30.0))

    # If user_id not explicitly given, try matching active user by email
    target_uid = user_id
    if not target_uid:
        match = query_one("SELECT user_id FROM Users WHERE email = %s", (email_clean,))
        if match:
            target_uid = match["user_id"]

    # Check for existing pending application for this email/station
    existing = query_one(
        "SELECT application_id FROM OwnerApplications "
        "WHERE email = %s AND station_name = %s AND application_status = 'PENDING'",
        (email_clean, station_name.strip())
    )
    if existing:
        return existing["application_id"], None

    app_id = execute(
        "INSERT INTO OwnerApplications (user_id, applicant_name, email, phone, company_name, "
        "                              station_name, city, state, pincode, proposed_chargers, "
        "                              power_capacity_kw, application_status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')",
        (
            target_uid,
            applicant_name.strip(),
            email_clean,
            phone.strip() if phone else None,
            company_name.strip() if company_name else None,
            station_name.strip(),
            city.strip(),
            state.strip() if state else None,
            pincode.strip() if pincode else None,
            chargers,
            power,
        )
    )

    if target_uid:
        try:
            add_notification(
                user_id=target_uid,
                title="Partner Application Received",
                message=f"Your Station Partner application for '{station_name.strip()}' has been received and is under review.",
                category="APPLICATION",
                link_url="/owner/apply",
            )
        except Exception:
            pass

    return app_id, None


def get_owner_applications(status=None, search=None):
    """Admin view: Retrieve station partner applications with reviewer details."""
    sql = (
        "SELECT oa.*, u.full_name AS registered_user_name, u.role AS current_role, "
        "       adm.full_name AS reviewer_name "
        "FROM OwnerApplications oa "
        "LEFT JOIN Users u ON u.user_id = oa.user_id "
        "LEFT JOIN Users adm ON adm.user_id = oa.reviewed_by_user_id "
        "WHERE 1=1 "
    )
    params = []
    if status and status.upper() in ("PENDING", "APPROVED", "REJECTED"):
        sql += " AND oa.application_status = %s"
        params.append(status.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        sql += " AND (oa.applicant_name LIKE %s OR oa.email LIKE %s OR oa.station_name LIKE %s OR oa.city LIKE %s)"
        params.extend([like, like, like, like])

    sql += " ORDER BY oa.created_at DESC"
    return query_all(sql, params)


def get_owner_application_by_id(app_id):
    """Retrieve application details by primary key."""
    return query_one(
        "SELECT oa.*, u.full_name AS registered_user_name, u.role AS current_role, "
        "       adm.full_name AS reviewer_name "
        "FROM OwnerApplications oa "
        "LEFT JOIN Users u ON u.user_id = oa.user_id "
        "LEFT JOIN Users adm ON adm.user_id = oa.reviewed_by_user_id "
        "WHERE oa.application_id = %s",
        (app_id,)
    )


def review_owner_application(application_id, admin_user_id, action, admin_notes=None, assign_station_id=None):
    """
    Admin workflow: Approve or reject an application.
    When APPROVED:
      - Transitions status to APPROVED.
      - Upgrades user role to 'OWNER'.
      - Optionally assigns a Station to this owner.
      - Sends in-app notification and audit log.
    """
    app = get_owner_application_by_id(application_id)
    if not app:
        return False, "Application not found."

    clean_action = (action or "").strip().upper()
    if clean_action not in ("APPROVED", "REJECTED"):
        return False, "Invalid review action (must be APPROVED or REJECTED)."

    notes = (admin_notes or "").strip() or None

    with transaction() as cur:
        cur.execute(
            "UPDATE OwnerApplications "
            "SET application_status = %s, admin_notes = %s, reviewed_by_user_id = %s, reviewed_at = NOW() "
            "WHERE application_id = %s",
            (clean_action, notes, admin_user_id, application_id)
        )

        target_uid = app.get("user_id")
        if not target_uid and app.get("email"):
            # Check if user registered after submitting application
            cur.execute("SELECT user_id FROM Users WHERE email = %s", (app["email"],))
            match = cur.fetchone()
            if match:
                target_uid = match["user_id"]
                cur.execute("UPDATE OwnerApplications SET user_id = %s WHERE application_id = %s", (target_uid, application_id))

        if clean_action == "APPROVED" and target_uid:
            cur.execute("UPDATE Users SET role = 'OWNER' WHERE user_id = %s", (target_uid,))
            if assign_station_id:
                cur.execute(
                    "UPDATE Stations SET owner_user_id = %s WHERE station_id = %s",
                    (target_uid, assign_station_id)
                )

    # Auditing and notifications
    log_audit_event(
        f"OWNER_APPLICATION_{clean_action}",
        "OwnerApplications",
        application_id,
        admin_user_id,
        f"Admin review {clean_action} for application #{application_id} ({app['email']})",
    )

    if target_uid:
        title = "Station Partner Approved!" if clean_action == "APPROVED" else "Partner Application Update"
        msg = (
            f"Congratulations! Your application for '{app['station_name']}' has been approved. You now have Station Partner privileges."
            if clean_action == "APPROVED"
            else f"Your application for '{app['station_name']}' was reviewed. Notes: {notes or 'Please contact support for feedback.'}"
        )
        try:
            add_notification(
                user_id=target_uid,
                title=title,
                message=msg,
                category="APPLICATION",
                link_url="/owner/dashboard" if clean_action == "APPROVED" else "/owner/apply",
            )
        except Exception:
            pass

    return True, None


# ============================================================================
# STATION OWNER (OPERATOR) SCOPED DATA
# ============================================================================

def get_owner_stations(owner_user_id):
    """Retrieve only the charging stations assigned to this owner."""
    try:
        return query_all(
            "SELECT s.*, "
            "       COUNT(DISTINCT cp.point_id) AS total_points, "
            "       SUM(CASE WHEN cp.point_status = 'AVAILABLE' THEN 1 ELSE 0 END) AS available_points, "
            "       SUM(CASE WHEN cp.point_status = 'CHARGING' THEN 1 ELSE 0 END) AS in_use_points, "
            "       MIN(cp.tariff_per_kwh) AS min_tariff, "
            "       MAX(cp.max_power_kw) AS max_power "
            "FROM Stations s "
            "LEFT JOIN ChargingPoints cp ON cp.station_id = s.station_id "
            "WHERE s.owner_user_id = %s "
            "GROUP BY s.station_id "
            "ORDER BY s.station_id ASC",
            (owner_user_id,)
        )
    except Exception:
        return []


def get_owner_station_by_id(station_id, owner_user_id):
    """Retrieve station ensuring it belongs to the authenticated owner."""
    try:
        return query_one(
            "SELECT * FROM Stations WHERE station_id = %s AND owner_user_id = %s",
            (station_id, owner_user_id)
        )
    except Exception:
        return None


def verify_owner_station_access(station_id, owner_user_id):
    """Return True if owner owns this station, False otherwise."""
    st = get_owner_station_by_id(station_id, owner_user_id)
    return bool(st)


def get_owner_charging_points(owner_user_id):
    """Retrieve all dispensers belonging to stations owned by this partner."""
    try:
        return query_all(
            "SELECT cp.*, s.station_name, s.city, s.address "
            "FROM ChargingPoints cp "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "WHERE s.owner_user_id = %s "
            "ORDER BY s.station_name ASC, cp.point_code ASC",
            (owner_user_id,)
        )
    except Exception:
        return []


def get_owner_bookings(owner_user_id):
    """Retrieve bookings for stations owned by this partner, including payment status."""
    try:
        return query_all(
            "SELECT b.*, u.full_name AS customer_name, u.email AS customer_email, u.phone AS customer_phone, "
            "       v.registration_no, v.make, v.model, "
            "       cp.point_code, cp.connector_type, "
            "       s.station_name, s.city, "
            "       p.payment_id, p.payment_status, p.amount AS payment_amount, p.payment_method "
            "FROM Bookings b "
            "JOIN Users u ON u.user_id = b.user_id "
            "JOIN Vehicles v ON v.vehicle_id = b.vehicle_id "
            "JOIN ChargingPoints cp ON cp.point_id = b.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "LEFT JOIN Payments p ON p.booking_id = b.booking_id "
            "WHERE s.owner_user_id = %s "
            "ORDER BY b.start_at DESC",
            (owner_user_id,)
        )
    except Exception:
        return []


def get_owner_sessions(owner_user_id):
    """Retrieve charging sessions for stations owned by this partner."""
    try:
        return query_all(
            "SELECT cs.*, u.full_name AS customer_name, u.email AS customer_email, "
            "       v.registration_no, v.make, v.model, "
            "       cp.point_code, cp.connector_type, "
            "       s.station_name, s.city, "
            "       p.payment_status, p.amount AS paid_amount, p.transaction_reference "
            "FROM ChargingSessions cs "
            "JOIN Users u ON u.user_id = cs.user_id "
            "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
            "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "LEFT JOIN Payments p ON p.session_id = cs.session_id "
            "WHERE s.owner_user_id = %s "
            "ORDER BY cs.start_at DESC",
            (owner_user_id,)
        )
    except Exception:
        return []


def get_owner_dashboard_kpis(owner_user_id):
    """Compute partner operations KPIs strictly scoped to owned stations."""
    kpis = {
        "station_count": 0,
        "point_count": 0,
        "active_bookings": 0,
        "total_kwh_delivered": 0.0,
        "total_revenue": 0.0,
    }

    try:
        # Station & Point counts
        counts = query_one(
            "SELECT COUNT(DISTINCT s.station_id) AS st_cnt, "
            "       COUNT(DISTINCT cp.point_id) AS pt_cnt "
            "FROM Stations s "
            "LEFT JOIN ChargingPoints cp ON cp.station_id = s.station_id "
            "WHERE s.owner_user_id = %s",
            (owner_user_id,)
        )
        if counts:
            kpis["station_count"] = int(counts.get("st_cnt") or 0)
            kpis["point_count"] = int(counts.get("pt_cnt") or 0)

        # Active upcoming bookings on owned points
        b_row = query_one(
            "SELECT COUNT(*) AS cnt "
            "FROM Bookings b "
            "JOIN ChargingPoints cp ON cp.point_id = b.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "WHERE s.owner_user_id = %s AND b.booking_status IN ('CONFIRMED', 'PENDING') AND b.end_at >= NOW()",
            (owner_user_id,)
        )
        if b_row:
            kpis["active_bookings"] = int(b_row.get("cnt") or 0)

        # Sessions stats
        sess_row = query_one(
            "SELECT COALESCE(SUM(cs.energy_kwh), 0) AS total_kwh, "
            "       COALESCE(SUM(cs.total_cost), 0) AS total_rev "
            "FROM ChargingSessions cs "
            "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "WHERE s.owner_user_id = %s",
            (owner_user_id,)
        )
        if sess_row:
            kpis["total_kwh_delivered"] = round(float(sess_row.get("total_kwh") or 0.0), 2)
            kpis["total_revenue"] = round(float(sess_row.get("total_rev") or 0.0), 2)
    except Exception:
        pass

    return kpis
