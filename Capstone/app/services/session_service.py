"""
Charging Session Service
EV Charging Station Management System - Production Hardened
"""
from app.db import query_all, query_one, call_proc, transaction


def start_session(user_id, vehicle_id, point_id, booking_id=None):
    """
    Initiate a simulated charging session inside an atomic transaction.
    Verifies vehicle ownership, dispenser availability (via FOR UPDATE lock),
    and booking ownership + point match if booking_id is supplied.
    """
    try:
        point_id_int = int(point_id)
        vehicle_id_int = int(vehicle_id)
    except (TypeError, ValueError):
        return None, "Invalid vehicle or charging point selection."

    booking_id_int = None
    if booking_id not in (None, ""):
        try:
            booking_id_int = int(booking_id)
        except (TypeError, ValueError):
            return None, "Invalid booking reference."

    # 1. Ownership check on vehicle
    veh = query_one(
        "SELECT vehicle_id FROM Vehicles WHERE vehicle_id = %s AND user_id = %s",
        (vehicle_id_int, user_id)
    )
    if not veh:
        return None, "Selected vehicle does not belong to your account."

    # 2. Atomic transaction with row-level locking
    with transaction() as cur:
        cur.execute(
            "SELECT cp.point_id, cp.point_status, cp.tariff_per_kwh, s.station_status "
            "FROM ChargingPoints cp "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "WHERE cp.point_id = %s FOR UPDATE",
            (point_id_int,)
        )
        point = cur.fetchone()
        if not point:
            return None, "Charging point not found."
        if point["point_status"] != "AVAILABLE" or point["station_status"] != "ACTIVE":
            return None, "Charging point is currently not available for charging."

        # 3. Check if user already has an active session in progress
        cur.execute(
            "SELECT session_id FROM ChargingSessions "
            "WHERE user_id = %s AND session_status = 'IN_PROGRESS' FOR UPDATE",
            (user_id,)
        )
        active = cur.fetchone()
        if active:
            return None, f"You already have an active session in progress (Session #{active['session_id']})."

        # 4. Validate booking ownership, dispenser match, and status if linked
        if booking_id_int is not None:
            cur.execute(
                "SELECT booking_id, user_id, point_id, booking_status "
                "FROM Bookings WHERE booking_id = %s FOR UPDATE",
                (booking_id_int,)
            )
            booking = cur.fetchone()
            if not booking:
                return None, "Linked booking not found."
            if int(booking["user_id"]) != int(user_id):
                return None, "Permission denied: Linked booking does not belong to your account."
            if int(booking["point_id"]) != point_id_int:
                return None, "Linked booking does not match the selected charging dispenser."
            if booking["booking_status"] not in ("PENDING", "CONFIRMED"):
                return None, f"Linked booking cannot be started (status: {booking['booking_status']})."

        cur.execute(
            "INSERT INTO ChargingSessions "
            "(booking_id, user_id, vehicle_id, point_id, start_at, energy_kwh, tariff_per_kwh, total_cost, session_status) "
            "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 0.000, %s, 0.00, 'IN_PROGRESS')",
            (booking_id_int, user_id, vehicle_id_int, point_id_int, point["tariff_per_kwh"])
        )
        session_id = cur.lastrowid

        cur.execute(
            "UPDATE ChargingPoints SET point_status = 'OCCUPIED' WHERE point_id = %s",
            (point_id_int,)
        )

        if booking_id_int is not None:
            cur.execute(
                "UPDATE Bookings SET booking_status = 'COMPLETED' WHERE booking_id = %s AND user_id = %s",
                (booking_id_int, user_id)
            )

    return session_id, None


def complete_session(session_id, energy_kwh, user_id=None):
    """
    Complete an active charging session by invoking the MySQL Stored Procedure:
    CompleteChargingSession(p_session_id, p_energy_kwh).
    """
    try:
        energy = float(energy_kwh)
    except (TypeError, ValueError):
        return None, "Invalid energy value supplied."

    if energy < 0:
        return None, "Energy consumed cannot be negative."

    session = query_one(
        "SELECT session_id, user_id, session_status FROM ChargingSessions WHERE session_id = %s",
        (session_id,)
    )
    if not session:
        return None, "Charging session not found."

    if user_id is not None and int(session["user_id"]) != int(user_id):
        return None, "Permission denied: Session does not belong to your account."

    if session["session_status"] != "IN_PROGRESS":
        return None, f"Session is not in progress (Current status: {session['session_status']})."

    try:
        call_proc("CompleteChargingSession", (session_id, energy))
        updated = query_one(
            "SELECT session_id, booking_id, user_id, vehicle_id, point_id, start_at, end_at, "
            "       energy_kwh, tariff_per_kwh, total_cost, session_status "
            "FROM ChargingSessions WHERE session_id = %s",
            (session_id,)
        )
        return updated, None
    except Exception as e:
        return None, f"Database procedure error: {str(e)}"


def get_active_session_for_user(user_id):
    """Retrieve currently active session for an EV Owner."""
    try:
        return query_one(
            "SELECT cs.*, v.registration_no, v.make, v.model, "
            "       cp.point_code, cp.connector_type, cp.max_power_kw, "
            "       s.station_name, s.city "
            "FROM ChargingSessions cs "
            "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
            "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "WHERE cs.user_id = %s AND cs.session_status = 'IN_PROGRESS' "
            "ORDER BY cs.start_at DESC LIMIT 1",
            (user_id,)
        )
    except Exception:
        return None


def get_session_by_id(session_id, user_id=None):
    """Retrieve full details of a single session with payment status."""
    sql = (
        "SELECT cs.*, v.registration_no, v.make, v.model, "
        "       cp.point_code, cp.connector_type, "
        "       s.station_name, s.city, "
        "       p.payment_id, p.payment_status, p.payment_method, p.transaction_reference, p.paid_at "
        "FROM ChargingSessions cs "
        "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "LEFT JOIN Payments p ON p.payment_id = ("
        "    SELECT p2.payment_id FROM Payments p2 WHERE p2.session_id = cs.session_id "
        "    ORDER BY (p2.payment_status = 'SUCCESS') DESC, p2.payment_id DESC LIMIT 1"
        ") "
        "WHERE cs.session_id = %s"
    )
    params = [session_id]
    if user_id is not None:
        sql += " AND cs.user_id = %s"
        params.append(user_id)
    try:
        return query_one(sql, params)
    except Exception:
        return None


def get_user_sessions(user_id):
    """Retrieve full history of charging sessions for an EV owner."""
    try:
        return query_all(
            "SELECT cs.*, v.registration_no, v.make, v.model, "
            "       cp.point_code, cp.connector_type, "
            "       s.station_name, s.city, "
            "       p.payment_id, p.payment_status, p.payment_method, p.transaction_reference, p.paid_at "
            "FROM ChargingSessions cs "
            "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
            "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "LEFT JOIN Payments p ON p.payment_id = ("
            "    SELECT p2.payment_id FROM Payments p2 WHERE p2.session_id = cs.session_id "
            "    ORDER BY (p2.payment_status = 'SUCCESS') DESC, p2.payment_id DESC LIMIT 1"
            ") "
            "WHERE cs.user_id = %s "
            "ORDER BY cs.start_at DESC",
            (user_id,)
        )
    except Exception:
        return []


def get_all_sessions():
    """Admin view: Retrieve all charging sessions system-wide."""
    try:
        return query_all(
            "SELECT cs.*, u.full_name AS user_name, u.email AS user_email, "
            "       v.registration_no, v.make, v.model, "
            "       cp.point_code, cp.connector_type, "
            "       s.station_name, s.city, "
            "       p.payment_id, p.payment_status, p.payment_method, p.transaction_reference "
            "FROM ChargingSessions cs "
            "JOIN Users u ON u.user_id = cs.user_id "
            "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
            "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
            "JOIN Stations s ON s.station_id = cp.station_id "
            "LEFT JOIN Payments p ON p.payment_id = ("
            "    SELECT p2.payment_id FROM Payments p2 WHERE p2.session_id = cs.session_id "
            "    ORDER BY (p2.payment_status = 'SUCCESS') DESC, p2.payment_id DESC LIMIT 1"
            ") "
            "ORDER BY cs.start_at DESC"
        )
    except Exception:
        return []


def get_session_receipt(session_id, user_id=None):
    """Retrieve full itemized receipt & invoice record for a completed charging session."""
    sql = (
        "SELECT cs.*, "
        "       u.full_name AS customer_name, u.email AS customer_email, u.phone AS customer_phone, "
        "       v.registration_no, v.make, v.model, v.battery_capacity_kwh, "
        "       cp.point_code, cp.connector_type, cp.max_power_kw, "
        "       s.station_name, s.address AS station_address, s.city AS station_city, "
        "       p.payment_id, p.payment_status, p.payment_method, p.transaction_reference, p.paid_at, "
        "       TIMESTAMPDIFF(MINUTE, cs.start_at, COALESCE(cs.end_at, NOW())) AS duration_minutes "
        "FROM ChargingSessions cs "
        "JOIN Users u ON u.user_id = cs.user_id "
        "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "LEFT JOIN Payments p ON p.payment_id = ("
        "    SELECT p2.payment_id FROM Payments p2 WHERE p2.session_id = cs.session_id "
        "    ORDER BY (p2.payment_status = 'SUCCESS') DESC, p2.payment_id DESC LIMIT 1"
        ") "
        "WHERE cs.session_id = %s"
    )
    params = [session_id]
    if user_id is not None:
        sql += " AND cs.user_id = %s"
        params.append(user_id)
    return query_one(sql, params)
