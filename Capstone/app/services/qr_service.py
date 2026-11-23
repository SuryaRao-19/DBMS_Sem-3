"""
Station Identification QR Service (Feature A)
Opaque Token Generation, PNG/SVG Export, Scan Telemetry & Admin Revocation
EV Charging Station Management System
"""
import io
import secrets
from datetime import datetime
import qrcode
import qrcode.image.svg

from app.db import query_one, query_all, execute
from app.services.audit_service import log_audit_event


def _new_qr_token():
    """Generate a high-entropy URL-safe opaque token (never exposes sequential DB IDs)."""
    return secrets.token_urlsafe(24)


def get_or_create_station_qr(station_id, admin_user_id=None):
    """Return active QR metadata for station_id, creating an opaque token if none exists."""
    try:
        row = query_one(
            "SELECT qr_id, station_id, qr_token, qr_status, expires_at, scan_count, last_scanned_at, created_at, revoked_at "
            "FROM StationQRCodes WHERE station_id = %s AND qr_status = 'ACTIVE' "
            "ORDER BY qr_id DESC LIMIT 1",
            (station_id,),
        )
        if row:
            return row

        token = _new_qr_token()
        execute(
            "INSERT INTO StationQRCodes (station_id, qr_token, qr_status, created_by) VALUES (%s, %s, 'ACTIVE', %s)",
            (station_id, token, admin_user_id),
        )
        return query_one(
            "SELECT qr_id, station_id, qr_token, qr_status, expires_at, scan_count, last_scanned_at, created_at, revoked_at "
            "FROM StationQRCodes WHERE qr_token = %s",
            (token,),
        )
    except Exception:
        return {
            "qr_id": 0,
            "station_id": station_id,
            "qr_token": f"station_demo_{station_id}",
            "qr_status": "ACTIVE",
            "expires_at": None,
            "scan_count": 0,
            "last_scanned_at": None,
            "created_at": datetime.now(),
            "revoked_at": None,
        }


def get_latest_station_qr(station_id):
    """Fetch latest QR record (ACTIVE or REVOKED) for admin inspection."""
    return query_one(
        "SELECT qr_id, station_id, qr_token, qr_status, expires_at, scan_count, last_scanned_at, created_at, revoked_at "
        "FROM StationQRCodes WHERE station_id = %s ORDER BY qr_id DESC LIMIT 1",
        (station_id,),
    )


def list_all_station_qrs():
    """Fetch latest QR telemetry keyed by station_id for admin management tables."""
    rows = query_all(
        "SELECT q1.qr_id, q1.station_id, q1.qr_token, q1.qr_status, q1.expires_at, "
        "       q1.scan_count, q1.last_scanned_at, q1.created_at, q1.revoked_at "
        "FROM StationQRCodes q1 "
        "INNER JOIN (SELECT station_id, MAX(qr_id) AS max_id FROM StationQRCodes GROUP BY station_id) q2 "
        "  ON q1.qr_id = q2.max_id"
    )
    return {r["station_id"]: r for r in rows}


def regenerate_station_qr(station_id, admin_user_id):
    """Revoke prior active QR tokens for a station and issue a fresh opaque token."""
    st = query_one("SELECT station_id, station_name FROM Stations WHERE station_id = %s", (station_id,))
    if not st:
        return None, "Charging station not found."

    now_dt = datetime.now()
    execute(
        "UPDATE StationQRCodes SET qr_status = 'REVOKED', revoked_at = %s "
        "WHERE station_id = %s AND qr_status = 'ACTIVE'",
        (now_dt, station_id),
    )
    new_token = _new_qr_token()
    execute(
        "INSERT INTO StationQRCodes (station_id, qr_token, qr_status, created_by) VALUES (%s, %s, 'ACTIVE', %s)",
        (station_id, new_token, admin_user_id),
    )
    log_audit_event(
        action="STATION_QR_REGENERATED",
        entity_name="StationQRCodes",
        entity_id=station_id,
        user_id=admin_user_id,
        details=f"Regenerated opaque Station Identification QR for '{st['station_name']}'",
    )
    return get_latest_station_qr(station_id), None


def revoke_station_qr(station_id, admin_user_id):
    """Revoke any active Station Identification QR token without issuing a replacement."""
    st = query_one("SELECT station_id, station_name FROM Stations WHERE station_id = %s", (station_id,))
    if not st:
        return False, "Charging station not found."

    affected = execute(
        "UPDATE StationQRCodes SET qr_status = 'REVOKED', revoked_at = %s "
        "WHERE station_id = %s AND qr_status = 'ACTIVE'",
        (datetime.now(), station_id),
    )
    if affected == 0:
        return False, "No active QR code found to revoke for this station."

    log_audit_event(
        action="STATION_QR_REVOKED",
        entity_name="StationQRCodes",
        entity_id=station_id,
        user_id=admin_user_id,
        details=f"Revoked Station Identification QR for '{st['station_name']}'",
    )
    return True, f"Station QR revoked for {st['station_name']}."


def record_qr_scan_by_token(qr_token):
    """
    Validate opaque Station QR token on scan.
    Returns (qr_record, error_message, status_code).
    """
    token = (qr_token or "").strip()
    if not token or len(token) < 8:
        return None, "Invalid or malformed Station QR code.", 404

    row = query_one(
        "SELECT q.qr_id, q.station_id, q.qr_token, q.qr_status, q.expires_at, q.scan_count, "
        "       q.last_scanned_at, s.station_slug, s.station_name, s.approval_status "
        "FROM StationQRCodes q "
        "JOIN Stations s ON s.station_id = q.station_id "
        "WHERE q.qr_token = %s",
        (token,),
    )
    if not row:
        return None, "Unrecognized Station QR code. This station tag does not exist.", 404
    if row["qr_status"] != "ACTIVE":
        return row, "This Station QR code has been revoked by an administrator.", 410
    if row.get("expires_at") and row["expires_at"] < datetime.now():
        return row, "This Station QR code has expired. Please request a fresh station sticker.", 410
    if row.get("approval_status") != "APPROVED":
        return row, "This station is pending administrative publication approval.", 403

    execute(
        "UPDATE StationQRCodes SET scan_count = scan_count + 1, last_scanned_at = %s WHERE qr_id = %s",
        (datetime.now(), row["qr_id"]),
    )
    row["scan_count"] = int(row["scan_count"] or 0) + 1
    return row, None, 200


def render_qr_png_bytes(target_url, box_size=10):
    """Generate PNG image bytes for a target QR URL in memory (serverless-safe)."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0B1220", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_qr_svg_bytes(target_url):
    """Generate crisp vector SVG bytes for a target QR URL in memory (serverless-safe)."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()



# ============================================================
# Charging Point (Dispenser) Identification QRs
# ============================================================

def get_or_create_point_qr(point_id, created_by=None):
    """Return the active Point Identification QR row for a dispenser, creating one if missing."""
    row = query_one(
        """
        SELECT qr_id, point_id, qr_token, qr_status, scan_count, last_scanned_at, created_at
        FROM PointQRCodes
        WHERE point_id = %s AND qr_status = 'ACTIVE'
        ORDER BY qr_id DESC
        LIMIT 1
        """,
        (point_id,),
    )
    if row:
        return row

    token = _new_qr_token()
    execute(
        "INSERT INTO PointQRCodes (point_id, qr_token, qr_status, scan_count, created_by) VALUES (%s, %s, 'ACTIVE', 0, %s)",
        (point_id, token, created_by),
    )
    return query_one(
        "SELECT qr_id, point_id, qr_token, qr_status, scan_count, last_scanned_at, created_at FROM PointQRCodes WHERE qr_token = %s",
        (token,),
    )


def list_all_point_qrs():
    """Return dict keyed by point_id for Admin dispenser QR inventory."""
    rows = query_all(
        """
        SELECT q.qr_id, q.point_id, q.qr_token, q.qr_status, q.scan_count, q.last_scanned_at
        FROM PointQRCodes q
        INNER JOIN (
            SELECT point_id, MAX(qr_id) AS max_qr_id
            FROM PointQRCodes
            GROUP BY point_id
        ) latest ON latest.max_qr_id = q.qr_id
        """
    )
    return {r["point_id"]: r for r in rows}


def regenerate_point_qr(point_id, created_by=None):
    """Revoke existing ACTIVE Point QR tokens and generate a fresh opaque token."""
    execute(
        "UPDATE PointQRCodes SET qr_status = 'REVOKED', revoked_at = NOW() WHERE point_id = %s AND qr_status = 'ACTIVE'",
        (point_id,),
    )
    token = _new_qr_token()
    execute(
        "INSERT INTO PointQRCodes (point_id, qr_token, qr_status, scan_count, created_by) VALUES (%s, %s, 'ACTIVE', 0, %s)",
        (point_id, token, created_by),
    )
    return token


def record_point_qr_scan_by_token(token):
    """Resolve an opaque Dispenser QR token and update scan count, rejecting revoked/missing tokens."""
    row = query_one(
        """
        SELECT pq.qr_id, pq.point_id, pq.qr_token, pq.qr_status, pq.scan_count,
               cp.point_code, cp.connector_type, cp.max_power_kw, cp.tariff_per_kwh, cp.point_status,
               s.station_id, s.station_name, s.station_slug, s.address, s.city, s.state,
               s.operator_name, s.provenance_category, s.verification_status
        FROM PointQRCodes pq
        JOIN ChargingPoints cp ON pq.point_id = cp.point_id
        JOIN Stations s ON cp.station_id = s.station_id
        WHERE pq.qr_token = %s
        LIMIT 1
        """,
        (token,),
    )
    if not row:
        return None, "Invalid or unknown Charging Point QR code.", 404
    if row["qr_status"] != "ACTIVE":
        return None, "This Charging Point QR placard has been revoked by an administrator.", 410

    execute(
        "UPDATE PointQRCodes SET scan_count = scan_count + 1, last_scanned_at = NOW() WHERE qr_id = %s",
        (row["qr_id"],),
    )
    row["scan_count"] = int(row.get("scan_count") or 0) + 1
    return row, None, 200


# ============================================================
# Booking Check-In Verification QRs (Strictly Scoped RBAC)
# ============================================================

def get_or_create_booking_qr(booking_id):
    """Return Booking Check-in Verification QR row for a booking, creating one if missing."""
    row = query_one(
        "SELECT qr_id, booking_id, qr_token, qr_status, verified_at, created_at FROM BookingQRCodes WHERE booking_id = %s LIMIT 1",
        (booking_id,),
    )
    if row:
        return row

    token = _new_qr_token()
    execute(
        "INSERT INTO BookingQRCodes (booking_id, qr_token, qr_status) VALUES (%s, %s, 'ACTIVE')",
        (booking_id, token),
    )
    return query_one(
        "SELECT qr_id, booking_id, qr_token, qr_status, verified_at, created_at FROM BookingQRCodes WHERE booking_id = %s LIMIT 1",
        (booking_id,),
    )


def list_booking_qrs_for_user(user_id):
    """Ensure every booking belonging to user_id has an active Booking QR and return dict by booking_id."""
    bookings = query_all("SELECT booking_id FROM Bookings WHERE user_id = %s", (user_id,))
    result = {}
    for b in bookings:
        result[b["booking_id"]] = get_or_create_booking_qr(b["booking_id"])
    return result


def get_booking_qr_by_token(token):
    """Fetch full booking verification metadata joined with user, vehicle, point, and station."""
    return query_one(
        """
        SELECT bq.qr_id, bq.booking_id, bq.qr_token, bq.qr_status, bq.verified_at,
               b.user_id, b.start_at, b.end_at, b.booking_status,
               u.full_name, u.email,
               v.registration_no, v.make, v.model,
               cp.point_id, cp.point_code, cp.connector_type, cp.max_power_kw,
               s.station_id, s.station_name, s.city, s.owner_user_id
        FROM BookingQRCodes bq
        JOIN Bookings b ON bq.booking_id = b.booking_id
        JOIN Users u ON b.user_id = u.user_id
        JOIN Vehicles v ON b.vehicle_id = v.vehicle_id
        JOIN ChargingPoints cp ON b.point_id = cp.point_id
        JOIN Stations s ON cp.station_id = s.station_id
        WHERE bq.qr_token = %s
        LIMIT 1
        """,
        (token,),
    )


def mark_booking_qr_verified(token):
    """Mark a Booking Check-in QR as USED after operator check-in verification."""
    row = get_booking_qr_by_token(token)
    if not row:
        return None, "Invalid Booking QR token.", 404
    if row["qr_status"] == "REVOKED":
        return None, "This Booking QR has been revoked.", 410
    execute(
        "UPDATE BookingQRCodes SET qr_status = 'USED', verified_at = NOW() WHERE qr_id = %s",
        (row["qr_id"],),
    )
    return get_booking_qr_by_token(token), None, 200


def resolve_any_qr_token(raw_input):
    """
    Unified resolver: accepts a full URL or raw opaque token and detects whether it is
    a Charging Point QR, Station QR, or Booking Check-in QR.
    Returns (result_dict, error_message, status_code).
    """
    val = (raw_input or "").strip()
    if not val:
        return None, "Empty QR code provided.", 400

    # Extract token if a full URL was provided
    if "/" in val:
        val = val.rstrip("/").split("/")[-1]
    if val.endswith(".png") or val.endswith(".svg"):
        val = val.rsplit(".", 1)[0]
    # Handle /qr/station/<token>/image.png or /qr/point/<token>/image.png
    if val in ("image", "scan", "check-in") and "/" in raw_input:
        parts = [p for p in raw_input.strip().rstrip("/").split("/") if p]
        if len(parts) >= 2:
            val = parts[-2]

    clean_token = val.strip()

    # 1. Try Dispenser / Charging Point QR
    pt_row, pt_err, _ = record_point_qr_scan_by_token(clean_token)
    if pt_row and not pt_err:
        return {
            "type": "POINT",
            "qr_type": "POINT",
            "token": clean_token,
            "point_id": pt_row["point_id"],
            "point_code": pt_row["point_code"],
            "connector_type": pt_row["connector_type"],
            "tariff_per_kwh": float(pt_row["tariff_per_kwh"] or 0),
            "max_power_kw": float(pt_row.get("max_power_kw") or 0),
            "station_id": pt_row["station_id"],
            "station_name": pt_row["station_name"],
            "city": pt_row["city"],
            "action_url": f"/customer/payments?tab=reserve&point_id={pt_row['point_id']}",
            "reserve_url": f"/customer/payments?tab=reserve&point_id={pt_row['point_id']}",
            "title": f"Charging Dispenser {pt_row['point_code']}",
            "description": f"{pt_row['station_name']} · {pt_row['connector_type']} · ₹{pt_row['tariff_per_kwh']}/kWh",
        }, None, 200

    # 2. Try Station Identification QR
    st_row, st_err, _ = record_qr_scan_by_token(clean_token)
    if st_row and not st_err:
        return {
            "type": "STATION",
            "qr_type": "STATION",
            "token": clean_token,
            "station_id": st_row["station_id"],
            "station_name": st_row["station_name"],
            "station_slug": st_row.get("station_slug"),
            "action_url": f"/customer/stations/{st_row['station_id']}",
            "reserve_url": f"/customer/payments?tab=reserve&station_id={st_row['station_id']}",
            "title": f"Station: {st_row['station_name']}",
            "description": "Public Charging Station Placard verified.",
        }, None, 200

    # 3. Try Booking Check-in QR
    bk_row = get_booking_qr_by_token(clean_token)
    if bk_row:
        return {
            "type": "BOOKING",
            "qr_type": "BOOKING",
            "token": clean_token,
            "booking_id": bk_row["booking_id"],
            "station_name": bk_row["station_name"],
            "point_code": bk_row["point_code"],
            "customer_name": bk_row["full_name"],
            "vehicle_reg": bk_row["registration_no"],
            "booking_status": bk_row["booking_status"],
            "action_url": f"/customer/bookings#{bk_row['booking_id']}",
            "title": f"Booking #{bk_row['booking_id']} Check-in",
            "description": f"{bk_row['station_name']} ({bk_row['point_code']}) for {bk_row['registration_no']}",
        }, None, 200

    # 4. Try Payment QR
    pay_row = query_one(
        "SELECT payment_id, session_id, booking_id, amount, payment_status, transaction_reference "
        "FROM Payments WHERE payment_qr_id = %s OR transaction_reference = %s OR razorpay_order_id = %s LIMIT 1",
        (clean_token, clean_token, clean_token),
    )
    if pay_row:
        target_url = (
            f"/customer/payment-result/{pay_row['payment_id']}"
            if pay_row["payment_status"] in ("SUCCESS", "PAID")
            else (f"/customer/checkout/{pay_row['session_id']}" if pay_row.get("session_id") else f"/customer/bookings/{pay_row.get('booking_id')}/checkout")
        )
        return {
            "type": "PAYMENT",
            "qr_type": "PAYMENT",
            "token": clean_token,
            "payment_id": pay_row["payment_id"],
            "amount": float(pay_row["amount"]),
            "payment_status": pay_row["payment_status"],
            "action_url": target_url,
            "title": f"Payment Transaction {pay_row['transaction_reference']}",
            "description": f"Status: {pay_row['payment_status']} · Amount: ₹{float(pay_row['amount']):.2f}",
        }, None, 200

    return None, "Unrecognized or invalid EV ChargeNet QR token.", 404
