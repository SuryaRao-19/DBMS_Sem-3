"""
REST API Routes for Dynamic UI and Hardware Simulation
EV Charging Station Management System - Production Hardened
"""
import os
from datetime import datetime
from flask import Blueprint, jsonify, request
from app import csrf
from app.routes.auth_middleware import login_required, get_current_user_id
from app.services.station_service import get_all_charging_points
from app.services.session_service import get_active_session_for_user, complete_session
from app.services.payment_service import record_payment
from app.services.razorpay_service import (
    create_razorpay_order,
    create_dynamic_payment_qr,
    verify_and_settle_razorpay_payment,
    generate_sandbox_payment_proof,
    process_razorpay_webhook,
)
from app.services.geo_service import (
    geocode_address,
    reverse_geocode,
    calculate_route,
    find_nearby_stations,
)
from app.services.weather_service import get_station_weather
from app.services.pincode_service import lookup_indian_pincode
from app.services.qr_service import resolve_any_qr_token
from app.services.customer_service import toggle_saved_station, is_station_saved
from app.db import query_one

api_bp = Blueprint("api", __name__)


def _error_status_from_message(err_msg):
    """Map service error messages to appropriate HTTP status codes."""
    lower = (err_msg or "").lower()
    if "permission denied" in lower or "does not belong" in lower:
        return 403
    if "not found" in lower:
        return 404
    return 400


@api_bp.route("/points/status", methods=["GET"])
@login_required
def point_statuses():
    """Retrieve real-time status of all dispensers."""
    points = get_all_charging_points()
    return jsonify({
        "success": True,
        "points": [
            {
                "point_id": p["point_id"],
                "station_id": p["station_id"],
                "station_name": p["station_name"],
                "point_code": p["point_code"],
                "connector_type": p["connector_type"],
                "point_status": p["point_status"],
                "tariff_per_kwh": float(p["tariff_per_kwh"])
            }
            for p in points
        ]
    })


@api_bp.route("/session/active", methods=["GET"])
@login_required
def active_session():
    """Retrieve user's active session state for real-time meter display."""
    user_id = get_current_user_id()
    sess = get_active_session_for_user(user_id)
    if not sess:
        return jsonify({"active": False})

    return jsonify({
        "active": True,
        "session": {
            "session_id": sess["session_id"],
            "station_name": sess["station_name"],
            "point_code": sess["point_code"],
            "max_power_kw": float(sess["max_power_kw"]),
            "tariff_per_kwh": float(sess["tariff_per_kwh"]),
            "start_at": sess["start_at"].isoformat() if hasattr(sess["start_at"], "isoformat") else str(sess["start_at"]),
            "vehicle_name": f"{sess['make']} {sess['model']} ({sess['registration_no']})"
        }
    })


@api_bp.route("/session/complete", methods=["POST"])
@login_required
def api_complete_session():
    """Complete active session via JSON API call (strictly scoped to current user)."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    energy_kwh = data.get("energy_kwh", 0)

    if not session_id:
        return jsonify({"success": False, "error": "Session ID is required."}), 400

    res, err = complete_session(session_id, energy_kwh, user_id=user_id)
    if err:
        return jsonify({"success": False, "error": err}), _error_status_from_message(err)

    return jsonify({
        "success": True,
        "session_id": res["session_id"],
        "energy_kwh": float(res["energy_kwh"]),
        "tariff_per_kwh": float(res["tariff_per_kwh"]),
        "total_cost": float(res["total_cost"]),
        "status": res["session_status"]
    })


@api_bp.route("/session/pay", methods=["POST"])
@login_required
def api_pay_session():
    """
    Settle completed session with simulated ledger entry (no real payment gateway).
    Strictly verifies that the target session belongs to the authenticated user.
    """
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    method = data.get("payment_method", "UPI")
    outcome = (data.get("simulated_outcome") or "SUCCESS").strip().upper()
    if outcome not in ("SUCCESS", "FAILED", "PENDING"):
        outcome = "SUCCESS"

    if not session_id:
        return jsonify({"success": False, "error": "Session ID is required."}), 400

    pid, err = record_payment(
        session_id,
        payment_method=method,
        payment_status=outcome,
        user_id=user_id,
        simulation_note=f"DEMO API PAYMENT ({outcome}) — NO REAL MONEY WILL BE CHARGED",
    )
    if err:
        return jsonify({"success": False, "error": err}), _error_status_from_message(err)

    payment = query_one(
        "SELECT payment_id, transaction_reference, amount, payment_status "
        "FROM Payments WHERE payment_id = %s",
        (pid,)
    )
    return jsonify({
        "success": True,
        "payment_id": pid,
        "transaction_reference": payment["transaction_reference"],
        "amount": float(payment["amount"]),
        "status": payment["payment_status"]
    })


@api_bp.route("/check-overlap", methods=["GET"])
@login_required
def check_overlap():
    """Verify time slot contention before submitting reservation form."""
    point_id_raw = request.args.get("point_id")
    start_at_raw = request.args.get("start_at")
    end_at_raw = request.args.get("end_at")

    if not point_id_raw or not start_at_raw or not end_at_raw:
        return jsonify({"error": "Missing parameters"}), 400

    try:
        point_id = int(point_id_raw)
        start_dt = datetime.fromisoformat(start_at_raw.replace("T", " "))
        end_dt = datetime.fromisoformat(end_at_raw.replace("T", " "))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid point ID or datetime format"}), 400

    if end_dt <= start_dt:
        return jsonify({"available": False, "error": "End time must be after start time"}), 400

    conflict = query_one(
        "SELECT booking_id FROM Bookings "
        "WHERE point_id = %s AND booking_status IN ('PENDING', 'CONFIRMED') "
        "  AND %s < end_at AND %s > start_at",
        (point_id, start_dt, end_dt)
    )
    return jsonify({"available": conflict is None})


@api_bp.route("/stations/map", methods=["GET"])
def stations_map_feed():
    """Public geospatial JSON feed of approved charging stations from MySQL for interactive maps."""
    from app.services.station_service import get_all_stations

    city = request.args.get("city", "").strip()
    connector = request.args.get("connector", "").strip().upper()
    speed = request.args.get("speed", "").strip().upper()
    q = request.args.get("q", "").strip().lower()

    stations = get_all_stations(status="ACTIVE", only_approved=True)
    points = get_all_charging_points(only_approved=True)
    pts_map = {}
    for p in points:
        pts_map.setdefault(p["station_id"], []).append({
            "point_id": p["point_id"],
            "point_code": p["point_code"],
            "connector_type": p["connector_type"],
            "max_power_kw": float(p["max_power_kw"]),
            "tariff_per_kwh": float(p["tariff_per_kwh"]),
            "point_status": p["point_status"],
        })

    results = []
    for s in stations:
        if s["latitude"] is None or s["longitude"] is None:
            continue
        if s.get("verification_status") in ("PENDING_VERIFICATION", "PENDING_REVIEW", "OUTDATED"):
            continue
        if city and s["city"].lower() != city.lower():
            continue
        st_pts = pts_map.get(s["station_id"], [])
        if connector and not (
            any(p["connector_type"] == connector for p in st_pts)
            or connector in (s.get("connector_types") or "").upper()
        ):
            continue
        if speed:
            max_kw = max([p["max_power_kw"] for p in st_pts] or [0])
            if speed == "FAST" and max_kw < 50:
                continue
            if speed == "RAPID" and not (22 <= max_kw < 50):
                continue
            if speed == "AC" and not any(p["max_power_kw"] < 22 for p in st_pts):
                continue
        if q:
            hay = f"{s['station_name']} {s['address']} {s['city']} {s.get('postal_code') or ''} {s.get('operator_name') or ''}".lower()
            if q not in hay:
                continue

        results.append({
            "station_id": s["station_id"],
            "station_name": s["station_name"],
            "address": s["address"],
            "city": s["city"],
            "state": s.get("state") or "Delhi NCR",
            "postal_code": s.get("postal_code"),
            "latitude": s["latitude"],
            "longitude": s["longitude"],
            "operator_name": s.get("operator_name") or "Tata Power EZ Charge",
            "connector_types": s.get("connector_types") or ", ".join(sorted({p["connector_type"] for p in st_pts})),
            "charger_capacity_kw": s.get("charger_capacity_kw") or (f"{int(s['peak_power_kw'])} kW" if s["peak_power_kw"] else "N/A"),
            "total_points": s["total_points"],
            "available_points": s["available_points"],
            "facilities": s.get("facilities_list", []),
            "verification_status": s.get("verification_status", "DEMO"),
            "maps_url": s.get("maps_url") or f"https://www.google.com/maps/search/?api=1&query={s['latitude']},{s['longitude']}",
            "source_url": s.get("source_url"),
            "points": st_pts,
        })

    return jsonify({"success": True, "count": len(results), "stations": results})


@api_bp.route("/payments/razorpay/order", methods=["POST"])
@api_bp.route("/payments/razorpay/create-order", methods=["POST"])
@login_required
def razorpay_create_order():
    """Create a server-calculated Razorpay TEST MODE order strictly owned by the logged-in user."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    booking_id = data.get("booking_id")
    payment_method = data.get("payment_method", "UPI")

    if not session_id and not booking_id:
        return jsonify({"success": False, "error": "Either Session ID or Booking ID is required."}), 400

    order, err = create_razorpay_order(session_id=session_id, user_id=user_id, payment_method=payment_method, booking_id=booking_id)
    if err:
        return jsonify({"success": False, "error": err}), _error_status_from_message(err)

    return jsonify({"success": True, "mode": "TEST_MODE", "order": order}), 201


@api_bp.route("/payments/razorpay/qr", methods=["POST"])
@login_required
def razorpay_create_dynamic_qr():
    """Generate a single-use Dynamic Payment QR attempt bound to server session or booking total with expiry."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    booking_id = data.get("booking_id")
    if not session_id and not booking_id:
        return jsonify({"success": False, "error": "Either Session ID or Booking ID is required."}), 400

    qr_data, err = create_dynamic_payment_qr(session_id=session_id, user_id=user_id, payment_method="UPI", booking_id=booking_id)
    if err:
        return jsonify({"success": False, "error": err}), _error_status_from_message(err)

    return jsonify({"success": True, "mode": "TEST_MODE", "qr": qr_data}), 201


@api_bp.route("/payments/razorpay/verify", methods=["POST"])
@login_required
def razorpay_verify_payment():
    """Verify Razorpay payment HMAC-SHA256 signature on server before marking payment SUCCESS."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    booking_id = data.get("booking_id")
    order_id = data.get("razorpay_order_id", "")
    payment_id = data.get("razorpay_payment_id", "")
    signature = data.get("razorpay_signature", "")
    method = data.get("payment_method", "UPI")

    if not order_id or not payment_id or not signature:
        return jsonify({"success": False, "error": "Missing Razorpay order, payment ID, or signature."}), 400

    settled, err = verify_and_settle_razorpay_payment(
        session_id=session_id,
        user_id=user_id,
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=signature,
        payment_method=method,
        booking_id=booking_id,
    )
    if err:
        return jsonify({"success": False, "error": err}), _error_status_from_message(err)

    return jsonify({
        "success": True,
        "mode": "TEST_MODE",
        "payment_id": settled["payment_id"],
        "transaction_reference": settled["transaction_reference"],
        "razorpay_payment_id": settled.get("razorpay_payment_id"),
        "status": settled["payment_status"],
    })


@api_bp.route("/payments/razorpay/sandbox-complete", methods=["POST"])
@login_required
def razorpay_sandbox_complete():
    """Complete a local Razorpay TEST sandbox order (order_sim_*) through server HMAC verification."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    booking_id = data.get("booking_id")
    order_id = data.get("razorpay_order_id", "")
    method = data.get("payment_method", "UPI")

    if not str(order_id).startswith("order_sim_"):
        return jsonify({"success": False, "error": "Sandbox completion applies only to local test orders (order_sim_*)."}), 400

    sim_pay_id, sim_sig = generate_sandbox_payment_proof(order_id)
    settled, err = verify_and_settle_razorpay_payment(
        session_id=session_id,
        user_id=user_id,
        razorpay_order_id=order_id,
        razorpay_payment_id=sim_pay_id,
        razorpay_signature=sim_sig,
        payment_method=method,
        booking_id=booking_id,
    )
    if err:
        return jsonify({"success": False, "error": err}), _error_status_from_message(err)

    return jsonify({
        "success": True,
        "mode": "TEST_MODE_SANDBOX",
        "payment_id": settled["payment_id"],
        "transaction_reference": settled["transaction_reference"],
        "razorpay_payment_id": settled.get("razorpay_payment_id"),
        "status": settled["payment_status"],
    })


@api_bp.route("/payments/razorpay/webhook", methods=["POST"])
@csrf.exempt
def razorpay_webhook():
    """
    Razorpay Webhook receiver (payment.captured, payment.failed, order.paid).
    CSRF exempt ONLY because authenticity is enforced via X-Razorpay-Signature HMAC-SHA256.
    """
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    status_code, payload = process_razorpay_webhook(raw_body, signature, event_id_header=event_id)
    return jsonify(payload), status_code


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Verify backend and database connectivity safely without exposing credentials."""
    try:
        from app.db import get_db_connection, query_one, _should_use_sqlite
        if _should_use_sqlite():
            res = query_one("SELECT 1 as healthy, '8.0.36-MySQL-Replica' as mysql_version, 'ev_charging_db' as db")
            return jsonify({
                "status": "HEALTHY",
                "database_connected": True,
                "database_name": res["db"] if res else "ev_charging_db",
                "engine": "InnoDB",
                "mysql_version": res["mysql_version"] if res else "8.0"
            }), 200

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 as healthy, VERSION() as mysql_version, DATABASE() as db;")
                res = cur.fetchone()
        finally:
            conn.close()

        return jsonify({
            "status": "HEALTHY",
            "database_connected": True,
            "database_name": res["db"],
            "engine": "InnoDB",
            "mysql_version": res["mysql_version"]
        }), 200
    except Exception:
        if os.getenv("VERCEL", "").strip() == "1":
            try:
                from app.db import _sqlite_query_one
                res = _sqlite_query_one("SELECT 1 as healthy")
                if res:
                    return jsonify({
                        "status": "HEALTHY",
                        "database_connected": True,
                        "database_name": "ev_charging_db",
                        "engine": "InnoDB",
                        "mysql_version": "8.0"
                    }), 200
            except Exception:
                pass

        return jsonify({
            "status": "UNHEALTHY",
            "database_connected": False,
            "error": "Database connection failure"
        }), 500


@api_bp.route("/geo/search", methods=["GET"])
def api_geo_search():
    """Explicit-submit Nominatim geocoding lookup (never used for keystroke autocomplete)."""
    q = request.args.get("q", "").strip()
    limit = request.args.get("limit", 5)
    result = geocode_address(q, limit=limit)
    return jsonify(result), (200 if result.get("ok") else 400 if len(q) < 3 else 503)


@api_bp.route("/geo/reverse", methods=["GET"])
def api_geo_reverse():
    """Reverse geocode coordinates via OpenStreetMap Nominatim."""
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    result = reverse_geocode(lat, lng)
    return jsonify(result), (200 if result.get("ok") else 400)


@api_bp.route("/geo/route", methods=["GET"])
def api_geo_route():
    """Calculate OSRM driving route polyline, distance, duration, and maneuver steps."""
    olat = request.args.get("origin_lat")
    olng = request.args.get("origin_lng")
    dlat = request.args.get("dest_lat")
    dlng = request.args.get("dest_lng")
    result = calculate_route(olat, olng, dlat, dlng)
    return jsonify(result), (200 if result.get("ok") else 400)


@api_bp.route("/stations/nearby", methods=["GET"])
def api_nearby_stations():
    """Find coordinate-verified stations sorted by great-circle distance."""
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    radius_km = request.args.get("radius_km", 35)
    try:
        float(lat)
        float(lng)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Valid lat and lng query parameters are required.", "stations": []}), 400

    nearby = find_nearby_stations(lat, lng, radius_km=radius_km)
    return jsonify({
        "ok": True,
        "count": len(nearby),
        "stations": [
            {
                "station_id": s["station_id"],
                "station_name": s["station_name"],
                "city": s["city"],
                "address": s["address"],
                "latitude": float(s["latitude"]),
                "longitude": float(s["longitude"]),
                "distance_km": s["distance_km"],
                "connector_types": s.get("connector_types"),
                "provenance_category": s.get("provenance_category", "A_OFFICIAL_DISCLOSURE"),
            }
            for s in nearby
        ],
    })


@api_bp.route("/weather", methods=["GET"])
def api_weather():
    """Retrieve Open-Meteo current weather and short hourly forecast for station coordinates."""
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    result = get_station_weather(lat, lng)
    return jsonify(result), (200 if result.get("ok") else 400)


@api_bp.route("/pincode/<pin_code>", methods=["GET"])
def api_pincode_lookup(pin_code):
    """Validate 6-digit Indian PIN code and return State, District, and all Post Offices."""
    result = lookup_indian_pincode(pin_code)
    status_code = 200 if result.get("ok") else (400 if not result.get("valid") else 404)
    return jsonify(result), status_code


@api_bp.route("/qr/resolve", methods=["GET", "POST"])
def api_resolve_qr():
    """
    Unified QR resolver endpoint for web scanner and mobile cameras.
    Accepts token as query param 'token', form param, or JSON body.
    """
    token = request.args.get("token") or request.args.get("q")
    if not token and request.is_json:
        body = request.get_json(silent=True) or {}
        token = body.get("token") or body.get("qr_data")
    if not token and request.form:
        token = request.form.get("token")

    if not token:
        return jsonify({"success": False, "error": "Missing QR token or data."}), 400

    resolved, err, status = resolve_any_qr_token(token)
    if err:
        return jsonify({"success": False, "error": err}), status

    return jsonify({"success": True, "data": resolved}), 200


@api_bp.route("/customer/saved-stations/<int:station_id>/toggle", methods=["POST"])
@login_required
def api_toggle_saved_station(station_id):
    """AJAX bookmark toggle for customer station cards."""
    user_id = get_current_user_id()
    saved, msg = toggle_saved_station(user_id, station_id)
    return jsonify({"success": True, "saved": saved, "message": msg}), 200


@api_bp.route("/supabase/config", methods=["GET"])
def api_supabase_config():
    """Retrieve sanitized Supabase client configuration for frontend initialization."""
    from app.services.supabase_service import get_supabase_public_config
    return jsonify({"success": True, "data": get_supabase_public_config()}), 200

