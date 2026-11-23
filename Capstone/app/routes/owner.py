"""
Charging Station Partner (Owner / Operator) Portal Routes
EV Charging Station Management System - Production Hardened
"""
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    Response,
    session,
)
from app.routes.auth_middleware import login_required, role_required, get_current_user_id, normalize_role
from app.services.owner_service import (
    submit_owner_application,
    get_owner_stations,
    get_owner_station_by_id,
    verify_owner_station_access,
    get_owner_charging_points,
    get_owner_bookings,
    get_owner_sessions,
    get_owner_dashboard_kpis,
)
from app.services.station_service import (
    create_station,
    update_station,
    create_charging_point,
    update_charging_point,
    get_point_by_id,
    get_all_stations,
)
from app.services.qr_service import (
    get_or_create_station_qr,
    get_or_create_point_qr,
    render_qr_png_bytes,
)
from app.services.auth_service import get_user_profile
from app.db import query_one, execute

owner_bp = Blueprint("owner", __name__)


# ----------------------------------------------------------------------------
# 1. Public / Customer Station Partner Application
# ----------------------------------------------------------------------------
@owner_bp.route("/apply", methods=["GET", "POST"])
def apply():
    """
    Public onboarding page where property owners, fleet hubs, and commercial
    hosts can apply to partner with the EV ChargeNet ecosystem.
    """
    uid = get_current_user_id()
    user = get_user_profile(uid) if uid else None

    # Check if this user already has a pending application
    existing_app = None
    if uid:
        existing_app = query_one(
            "SELECT * FROM OwnerApplications WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (uid,)
        )

    if request.method == "POST":
        applicant_name = request.form.get("applicant_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        company_name = request.form.get("company_name", "").strip()
        station_name = request.form.get("station_name", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        pincode = request.form.get("pincode", "").strip()
        chargers = request.form.get("proposed_chargers", 2)
        power_kw = request.form.get("power_capacity_kw", 60.0)

        app_id, err = submit_owner_application(
            applicant_name=applicant_name,
            email=email,
            phone=phone,
            company_name=company_name,
            station_name=station_name,
            city=city,
            state=state,
            pincode=pincode,
            proposed_chargers=chargers,
            power_capacity_kw=power_kw,
            user_id=uid,
        )
        if err:
            flash(err, "danger")
        else:
            flash(
                "Your Station Partner application has been received! Our network team will review your location within 2 business days.",
                "success",
            )
            return redirect(url_for("owner.apply"))

    return render_template("owner/apply.html", user=user, existing_app=existing_app)


# ----------------------------------------------------------------------------
# Access Guard & Scope Checking
# ----------------------------------------------------------------------------
@owner_bp.before_request
def check_owner_or_redirect():
    # Allow public access to /owner/apply
    if request.endpoint == "owner.apply":
        return None

    # If not logged in, require login
    uid = get_current_user_id()
    if not uid:
        return redirect(url_for("auth.login", next=request.url))

    role = normalize_role(session.get("role"))
    # Restrict Station Partner hardware management endpoints to OWNER / ADMIN
    if role == "CUSTOMER":
        path = request.path
        if path.startswith("/owner/stations") or path.startswith("/owner/points") or path.startswith("/owner/sessions"):
            abort(403)


# ----------------------------------------------------------------------------
# 2. Partner Dashboard (or Customer Dashboard for Drivers)
# ----------------------------------------------------------------------------
@owner_bp.route("/dashboard")
@login_required
def dashboard():
    uid = get_current_user_id()
    role = normalize_role(session.get("role"))
    if role == "ADMIN":
        abort(403)
    if role == "CUSTOMER":
        from app.routes.customer import dashboard as cust_dashboard
        return cust_dashboard()

    kpis = get_owner_dashboard_kpis(uid)
    stations = get_owner_stations(uid)
    recent_bookings = get_owner_bookings(uid)[:5]
    recent_sessions = get_owner_sessions(uid)[:5]
    return render_template(
        "owner/dashboard.html",
        kpis=kpis,
        stations=stations,
        recent_bookings=recent_bookings,
        recent_sessions=recent_sessions,
    )


# ----------------------------------------------------------------------------
# 3. My Charging Stations (Scoped to Owner)
# ----------------------------------------------------------------------------
@owner_bp.route("/stations")
@login_required
@role_required("OWNER")
def stations():
    uid = get_current_user_id()
    owned_stations = get_owner_stations(uid)
    return render_template("owner/stations.html", stations=owned_stations)


@owner_bp.route("/stations/<int:station_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("OWNER")
def station_edit(station_id):
    uid = get_current_user_id()
    st = get_owner_station_by_id(station_id, uid)
    if not st:
        abort(403)

    if request.method == "POST":
        address = request.form.get("address", "").strip()
        operating_hours = request.form.get("operating_hours", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        status = request.form.get("station_status", "ACTIVE")

        execute(
            "UPDATE Stations SET address = %s, operating_hours = %s, contact_phone = %s, station_status = %s "
            "WHERE station_id = %s AND owner_user_id = %s",
            (address, operating_hours, contact_phone, status, station_id, uid)
        )
        flash(f"Station '{st['station_name']}' settings updated.", "success")
        return redirect(url_for("owner.stations"))

    return render_template("owner/station_edit.html", station=st)


# ----------------------------------------------------------------------------
# 4. Charging Points & Tariffs (Scoped to Owned Stations)
# ----------------------------------------------------------------------------
@owner_bp.route("/points", methods=["GET"])
@login_required
@role_required("OWNER")
def points():
    uid = get_current_user_id()
    owned_points = get_owner_charging_points(uid)
    owned_stations = get_owner_stations(uid)
    return render_template("owner/points.html", points=owned_points, stations=owned_stations)


@owner_bp.route("/points/create", methods=["POST"])
@login_required
@role_required("OWNER")
def point_create():
    uid = get_current_user_id()
    station_id = request.form.get("station_id")
    if not verify_owner_station_access(station_id, uid):
        abort(403)

    point_code = request.form.get("point_code", "").strip().upper()
    connector_type = request.form.get("connector_type", "CCS2")
    power_kw = float(request.form.get("power_rating_kw", 30.0))
    tariff = float(request.form.get("tariff_per_kwh", 18.0))

    pid, err = create_charging_point(
        station_id=station_id,
        point_code=point_code,
        connector_type=connector_type,
        max_power_kw=power_kw,
        tariff_per_kwh=tariff,
        point_status="AVAILABLE",
    )
    if err:
        flash(err, "danger")
    else:
        flash(f"Dispenser '{point_code}' added to your station.", "success")
    return redirect(url_for("owner.points"))


@owner_bp.route("/points/<int:point_id>/edit", methods=["POST"])
@login_required
@role_required("OWNER")
def point_edit(point_id):
    uid = get_current_user_id()
    pt = get_point_by_id(point_id)
    if not pt or not verify_owner_station_access(pt["station_id"], uid):
        abort(403)

    tariff = float(request.form.get("tariff_per_kwh", pt["tariff_per_kwh"]))
    status = request.form.get("point_status", pt["point_status"])

    execute(
        "UPDATE ChargingPoints SET tariff_per_kwh = %s, point_status = %s WHERE point_id = %s",
        (tariff, status, point_id)
    )
    flash(f"Dispenser '{pt['point_code']}' configuration updated.", "success")
    return redirect(url_for("owner.points"))


# ----------------------------------------------------------------------------
# 5. Station Partner Bookings & Session Telemetry
# ----------------------------------------------------------------------------
@owner_bp.route("/bookings")
@login_required
def bookings():
    uid = get_current_user_id()
    role = normalize_role(session.get("role"))
    if role == "CUSTOMER":
        from app.routes.customer import bookings as cust_bookings
        return cust_bookings()

    partner_bookings = get_owner_bookings(uid)
    return render_template("owner/bookings.html", bookings=partner_bookings)


@owner_bp.route("/bookings/<int:booking_id>/qr.png", endpoint="booking_qr_png")
@login_required
def booking_qr_png(booking_id):
    from app.routes.customer import booking_qr_png as cust_qr_png
    return cust_qr_png(booking_id)


@owner_bp.route("/bookings/<int:booking_id>/cancel", endpoint="cancel_my_booking", methods=["POST"])
@login_required
def cancel_my_booking(booking_id):
    from app.routes.customer import booking_cancel
    return booking_cancel(booking_id)


@owner_bp.route("/payments/<int:payment_id>/collect-cash", methods=["POST"])
@login_required
@role_required("OWNER")
def collect_cash_payment(payment_id):
    """Confirm receipt of offline cash payment at station counter / bay for owner's station."""
    owner_id = get_current_user_id()
    notes = request.form.get("notes", "Cash collected at station counter / bay by operator").strip()

    payment = query_one(
        "SELECT p.*, b.booking_id, b.user_id, s.station_id, s.station_name, s.owner_user_id "
        "FROM Payments p "
        "LEFT JOIN Bookings b ON b.booking_id = p.booking_id "
        "LEFT JOIN ChargingPoints cp ON cp.point_id = b.point_id "
        "LEFT JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE p.payment_id = %s",
        (payment_id,)
    )
    if not payment:
        flash("Payment record not found.", "danger")
        return redirect(url_for("owner.bookings"))

    # Verify authorization: station must belong to the logged-in owner
    if payment.get("owner_user_id") != owner_id:
        flash("Unauthorized: You can only collect payments for your own charging hubs.", "danger")
        return redirect(url_for("owner.bookings"))

    if payment["payment_status"] != "PAYMENT_DUE":
        flash(f"Payment #{payment_id} is in status '{payment['payment_status']}' and cannot be recollected.", "warning")
        return redirect(url_for("owner.bookings"))

    execute(
        "UPDATE Payments "
        "SET payment_status = 'SUCCESS', "
        "    paid_at = NOW(), "
        "    cash_collected_by = %s, "
        "    cash_collected_at = NOW(), "
        "    cash_notes = %s "
        "WHERE payment_id = %s",
        (owner_id, notes, payment_id)
    )

    if payment.get("booking_id"):
        execute(
            "UPDATE Bookings SET booking_status = 'CONFIRMED' WHERE booking_id = %s",
            (payment["booking_id"],)
        )

    try:
        from app.services.audit_service import log_audit_event
        log_audit_event(
            action="COLLECT_CASH_PAYMENT",
            entity_name="Payments",
            entity_id=payment_id,
            user_id=owner_id,
            details=f"Station Partner #{owner_id} collected cash of ₹{payment['amount']} for Payment #{payment_id} (Booking #{payment.get('booking_id')})",
            ip_address=request.remote_addr,
        )
    except Exception:
        pass

    if payment.get("user_id"):
        try:
            from app.services.notification_service import add_notification
            add_notification(
                user_id=payment["user_id"],
                title="Cash Payment Received & Confirmed",
                message=f"Cash payment of ₹{float(payment['amount']):.2f} for booking #{payment.get('booking_id')} was confirmed by station operator at {payment.get('station_name', 'the station')}.",
                link="/customer/payments",
            )
        except Exception:
            pass

    flash(f"Cash payment of ₹{float(payment['amount']):.2f} for Booking #{payment.get('booking_id')} confirmed! Slot confirmed.", "success")
    return redirect(url_for("owner.bookings"))


@owner_bp.route("/sessions")
@login_required
@role_required("OWNER")
def sessions():
    uid = get_current_user_id()
    partner_sessions = get_owner_sessions(uid)
    return render_template("owner/sessions.html", sessions=partner_sessions)


# ----------------------------------------------------------------------------
# 6. Backward Compatibility Routes (Vehicles, Charging, History, Checkout, Receipts)
# ----------------------------------------------------------------------------
@owner_bp.route("/vehicles", endpoint="vehicles", methods=["GET", "POST"])
@login_required
def vehicles():
    from app.routes.customer import vehicles as cust_vehicles
    return cust_vehicles()


@owner_bp.route("/vehicles/<int:vehicle_id>/delete", endpoint="remove_vehicle", methods=["POST"])
@login_required
def remove_vehicle(vehicle_id):
    from app.routes.customer import vehicle_delete
    return vehicle_delete(vehicle_id)


@owner_bp.route("/book/<int:point_id>", endpoint="book_slot", methods=["GET", "POST"])
@login_required
def book_slot(point_id):
    from app.routes.customer import book_slot as cust_book_slot
    return cust_book_slot(point_id)


@owner_bp.route("/history", endpoint="history")
@login_required
def history():
    from app.services.session_service import get_user_sessions
    uid = get_current_user_id()
    my_sessions = get_user_sessions(uid)
    return render_template("owner/history.html", sessions=my_sessions)


@owner_bp.route("/session/<int:session_id>", endpoint="session_receipt")
@login_required
def session_receipt(session_id):
    from app.services.session_service import get_session_receipt
    uid = get_current_user_id()
    receipt = get_session_receipt(session_id, user_id=uid)
    if not receipt:
        flash("Charging session receipt not found or access denied.", "danger")
        return redirect(url_for("owner.history"))
    return render_template("owner/receipt.html", receipt=receipt)


@owner_bp.route("/session/<int:session_id>/download", endpoint="download_receipt")
@login_required
def download_receipt(session_id):
    from app.services.session_service import get_session_receipt
    uid = get_current_user_id()
    receipt = get_session_receipt(session_id, user_id=uid)
    if not receipt:
        flash("Charging session receipt not found or access denied.", "danger")
        return redirect(url_for("owner.history"))

    lines = [
        "EV CHARGENET — DEMO PAYMENT RECEIPT (NO REAL MONEY CHARGED)",
        "==============================================================",
        f"Invoice Number      : INV-{receipt['session_id']}",
        f"Session ID          : #{receipt['session_id']}",
        f"Booking Reference   : {('#' + str(receipt['booking_id'])) if receipt.get('booking_id') else 'Walk-in Direct Session'}",
        f"Driver              : {receipt['customer_name']} ({receipt['customer_email']})",
        f"Vehicle             : {receipt['make']} {receipt['model']} ({receipt['registration_no']})",
        f"Station             : {receipt['station_name']} — {receipt['station_address']}, {receipt['station_city']}",
        f"Dispenser           : {receipt['point_code']} ({receipt['connector_type']}, {receipt['max_power_kw']} kW)",
        f"Energy Delivered    : {receipt['energy_kwh']:.3f} kWh",
        f"Tariff              : INR {receipt['tariff_per_kwh']:.2f} / kWh",
        f"Total Amount        : INR {receipt['total_cost']:.2f} (DEMO LEDGER)",
        f"Payment Method      : {receipt.get('payment_method') or 'N/A'}",
        f"Payment Status      : {receipt.get('payment_status') or 'PENDING'}",
        f"Transaction Ref     : {receipt.get('transaction_reference') or 'N/A'}",
        f"Paid Timestamp      : {receipt.get('paid_at') or 'N/A'}",
        "==============================================================",
        "Academic Demonstration Disclaimer: Strictly simulated ledger transaction.",
    ]
    return Response(
        "\n".join(lines),
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=ev_demo_receipt_{session_id}.txt"},
    )


@owner_bp.route("/checkout/<int:session_id>", endpoint="checkout")
@login_required
def checkout(session_id):
    from app.services.razorpay_service import get_checkout_context, has_live_test_credentials, get_razorpay_credentials

    uid = get_current_user_id()
    ctx, err = get_checkout_context(session_id, uid)
    if err:
        if "permission denied" in err.lower():
            abort(403)
        flash(err, "danger")
        return redirect(url_for("owner.history"))

    creds = get_razorpay_credentials()
    return render_template(
        "owner/checkout.html",
        checkout=ctx,
        razorpay_key_id=creds["key_id"] if has_live_test_credentials(creds) else "",
        razorpay_live_test_ready=has_live_test_credentials(creds),
    )


@owner_bp.route("/charging", endpoint="charging", methods=["GET", "POST"])
@login_required
def charging():
    from app.services.session_service import (
        start_session, complete_session, get_active_session_for_user,
    )
    from app.services.vehicle_service import get_vehicles_by_user
    from app.services.station_service import get_all_charging_points
    from app.services.payment_service import record_payment

    uid = get_current_user_id()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "start":
            booking_id = request.form.get("booking_id")
            if booking_id:
                try:
                    booking_id = int(booking_id)
                except (ValueError, TypeError):
                    booking_id = None
            if booking_id:
                b_row = query_one("SELECT user_id FROM Bookings WHERE booking_id = %s", (booking_id,))
                if not b_row or b_row["user_id"] != uid:
                    abort(403)
            vehicle_id = request.form.get("vehicle_id")
            point_id = request.form.get("point_id")
            sid, err = start_session(user_id=uid, vehicle_id=vehicle_id, point_id=point_id, booking_id=booking_id)
            if err:
                if "permission denied" in err.lower():
                    abort(403)
                flash(err, "danger")
            else:
                flash(f"Charging session #{sid} initiated.", "success")
            return redirect(url_for("owner.charging"))
        elif action == "stop":
            sid = request.form.get("session_id")
            energy = float(request.form.get("energy_kwh", 15.0))
            ok, err = complete_session(sid, energy, user_id=uid)
            if err:
                if "permission denied" in err.lower():
                    abort(403)
                flash(err, "danger")
            else:
                flash("Charging session completed. Please proceed to payment.", "success")
                return redirect(url_for("owner.checkout", session_id=sid))
            return redirect(url_for("owner.charging"))
        elif action == "pay":
            sid = request.form.get("session_id")
            method = request.form.get("payment_method", "DEMO_PORTAL")
            sim_outcome = (request.form.get("simulated_outcome") or "SUCCESS").strip().upper()
            if sim_outcome not in ("SUCCESS", "FAILED", "PENDING"):
                sim_outcome = "SUCCESS"

            s_row = query_one("SELECT user_id FROM ChargingSessions WHERE session_id = %s", (sid,))
            if not s_row:
                abort(404)
            if s_row["user_id"] != uid:
                abort(403)

            payment_id, err = record_payment(
                sid,
                payment_method=method,
                payment_status=sim_outcome,
                user_id=uid,
                simulation_note=f"DEMO PAYMENT ({sim_outcome}) — NO REAL MONEY WILL BE CHARGED",
            )
            if err:
                if "permission denied" in err.lower():
                    abort(403)
                flash(err, "danger")
                return redirect(url_for("owner.history"))
            if sim_outcome == "SUCCESS":
                flash("DEMO PAYMENT SUCCESSFUL — No real money was charged. Receipt generated in ledger.", "success")
            elif sim_outcome == "FAILED":
                flash("DEMO PAYMENT SIMULATED FAILURE — Record logged cleanly. You may retry payment anytime.", "warning")
            else:
                flash("DEMO PAYMENT PENDING — Awaiting simulated settlement confirmation in ledger.", "info")
            return redirect(url_for("owner.history"))

    active_session = get_active_session_for_user(uid)
    vehicles = get_vehicles_by_user(uid)
    points = get_all_charging_points()
    return render_template("owner/charging.html", active_session=active_session, vehicles=vehicles, points=points)
