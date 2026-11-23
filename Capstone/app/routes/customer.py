"""
Customer Mobility Portal Routes
EV Charging Station Management System - Production Hardened
"""
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    Response,
    current_app,
    abort,
)
from app.routes.auth_middleware import login_required, role_required, get_current_user_id, normalize_role
from app.services.customer_service import (
    get_customer_dashboard_kpis,
    get_customer_recent_activity,
    get_saved_stations_for_user,
    toggle_saved_station,
    is_station_saved,
    get_customer_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    get_customer_charging_history,
    generate_customer_history_csv,
    get_customer_payments,
    get_customer_payment_summary,
    add_notification,
)
from app.services.vehicle_service import (
    get_vehicles_by_user,
    get_vehicle_by_id,
    add_vehicle,
    update_vehicle,
    delete_vehicle,
    set_default_vehicle,
)
from app.services.booking_service import (
    create_booking,
    get_user_bookings,
    cancel_booking,
)
from app.services.session_service import (
    start_session,
    complete_session,
    get_active_session_for_user,
    get_session_receipt,
)
from app.services.station_service import (
    get_all_stations,
    get_station_by_id,
    get_point_by_id,
    get_all_charging_points,
)
from app.services.razorpay_service import (
    get_checkout_context,
    get_booking_checkout_context,
    get_razorpay_credentials,
)
from app.services.qr_service import (
    get_or_create_booking_qr,
    get_or_create_station_qr,
    render_qr_png_bytes,
)
from app.services.api_health_service import get_station_provenance_meta
from app.services.weather_service import get_station_weather
from app.services.auth_service import (
    get_user_profile,
    update_user_profile,
    save_uploaded_avatar,
)
from app.services.contact_service import (
    submit_contact_enquiry,
    CONTACT_CATEGORIES,
    get_support_categories,
)
from app.db import query_all, query_one, execute

customer_bp = Blueprint("customer", __name__)


# ----------------------------------------------------------------------------
# 1. Dashboard / Overview
# ----------------------------------------------------------------------------
@customer_bp.route("/dashboard")
@login_required
@role_required("CUSTOMER")
def dashboard():
    uid = get_current_user_id()
    kpis = get_customer_dashboard_kpis(uid)
    recent_bookings, recent_sessions = get_customer_recent_activity(uid, limit=5)
    active_session = get_active_session_for_user(uid)
    vehicles = get_vehicles_by_user(uid)
    saved_stations = get_saved_stations_for_user(uid)[:4]
    return render_template(
        "customer/dashboard.html",
        kpis=kpis,
        recent_bookings=recent_bookings,
        recent_sessions=recent_sessions,
        active_session=active_session,
        vehicles=vehicles,
        saved_stations=saved_stations,
    )


# ----------------------------------------------------------------------------
# 2. Find Charging Stations
# ----------------------------------------------------------------------------
@customer_bp.route("/stations")
@login_required
@role_required("CUSTOMER")
def stations():
    uid = get_current_user_id()
    city_filter = request.args.get("city")
    status_filter = request.args.get("status")
    operator_filter = request.args.get("operator")
    connector_filter = request.args.get("connector")
    min_power_filter = request.args.get("min_power")
    search_query = request.args.get("q", "").strip()

    all_stations = get_all_stations(
        city=city_filter,
        status=status_filter,
        operator=operator_filter,
        connector=connector_filter,
        min_power=min_power_filter,
        q=search_query,
    )

    # Annotate with user bookmark status
    saved_rows = query_all("SELECT station_id FROM SavedStations WHERE user_id = %s", (uid,))
    saved_ids = {r["station_id"] for r in saved_rows}
    for s in all_stations:
        s["is_saved"] = s["station_id"] in saved_ids

    cities = query_all("SELECT DISTINCT city FROM Stations WHERE city IS NOT NULL ORDER BY city")
    operators = query_all("SELECT DISTINCT operator_name FROM Stations WHERE operator_name IS NOT NULL ORDER BY operator_name")
    return render_template(
        "customer/stations.html",
        stations=all_stations,
        cities=[c["city"] for c in cities],
        operators=[o["operator_name"] for o in operators],
        selected_city=city_filter,
        selected_operator=operator_filter,
        selected_connector=connector_filter,
        selected_min_power=min_power_filter,
        search_query=search_query,
    )


@customer_bp.route("/stations/<int:station_id>", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def station_detail(station_id):
    """Authenticated Customer view of station specs, dispensers, compatibility, and reservation entry."""
    uid = get_current_user_id()
    station = get_station_by_id(station_id, only_approved=True)
    if not station:
        flash("Charging station not found or pending verification.", "danger")
        return redirect(url_for("customer.stations"))

    prov = get_station_provenance_meta(station["station_id"])
    if prov:
        station.update(prov)
    station_qr = get_or_create_station_qr(station["station_id"])
    user_vehicles = get_vehicles_by_user(uid)

    # Check connector compatibility for each dispenser against customer's registered EVs
    points = station.get("points") or []
    for pt in points:
        pt_conn = (pt.get("connector_type") or "").upper()
        matching_vehs = []
        for v in user_vehicles:
            v_conn = (v.get("connector_type") or "").upper()
            if not v_conn or v_conn == pt_conn or (pt_conn in ("CCS2", "TYPE2") and v_conn in ("CCS2", "TYPE2")):
                matching_vehs.append(f"{v['make']} {v['model']} ({v['registration_no']})")
        pt["compatible_vehicles"] = matching_vehs
        pt["is_compatible"] = len(matching_vehs) > 0 or len(user_vehicles) == 0

    # Live weather at station coordinates
    weather = None
    if station.get("latitude") and station.get("longitude"):
        try:
            weather = get_station_weather(station["latitude"], station["longitude"])
        except Exception:
            weather = None

    # Bookmark state
    from app.services.customer_service import is_station_saved
    saved = is_station_saved(uid, station_id)

    return render_template(
        "customer/station_detail.html",
        station=station,
        points=points,
        station_qr=station_qr,
        vehicles=user_vehicles,
        weather=weather,
        is_saved=bool(saved),
    )


# ----------------------------------------------------------------------------
# 3. My Vehicles
# ----------------------------------------------------------------------------
@customer_bp.route("/vehicles", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def vehicles():
    uid = get_current_user_id()
    user_vehicles = get_vehicles_by_user(uid)
    return render_template("customer/vehicles.html", vehicles=user_vehicles)


@customer_bp.route("/vehicles/add", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def vehicle_add():
    if request.method == "GET":
        return redirect(url_for("customer.vehicles"))
    uid = get_current_user_id()
    reg = request.form.get("registration_no", "").strip().upper()
    make = request.form.get("make", "").strip()
    model = request.form.get("model", "").strip()
    capacity = request.form.get("battery_capacity_kwh", "")
    category = request.form.get("vehicle_category", "4W_SUV")
    connector = request.form.get("connector_type", "CCS2")
    year = request.form.get("registration_year") or None
    is_default = request.form.get("is_default") in ("1", "true", "on")

    vid, err = add_vehicle(
        user_id=uid,
        registration_no=reg,
        make=make,
        model=model,
        battery_capacity_kwh=capacity,
        vehicle_category=category,
        connector_type=connector,
        registration_year=year,
        is_default=is_default,
    )
    if err:
        flash(err, "danger")
    else:
        flash(f"Vehicle '{make} {model}' ({reg}) registered successfully!", "success")
    return redirect(url_for("customer.vehicles"))


@customer_bp.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def vehicle_edit(vehicle_id):
    if request.method == "GET":
        return redirect(url_for("customer.vehicles"))
    uid = get_current_user_id()
    reg = request.form.get("registration_no", "").strip().upper()
    make = request.form.get("make", "").strip()
    model = request.form.get("model", "").strip()
    capacity = request.form.get("battery_capacity_kwh", "")
    category = request.form.get("vehicle_category")
    connector = request.form.get("connector_type")
    year = request.form.get("registration_year")
    is_default = request.form.get("is_default") in ("1", "true", "on")

    ok, err = update_vehicle(
        vehicle_id=vehicle_id,
        user_id=uid,
        registration_no=reg,
        make=make,
        model=model,
        battery_capacity_kwh=capacity,
        vehicle_category=category,
        connector_type=connector,
        registration_year=year,
        is_default=is_default,
    )
    if not ok:
        flash(err, "danger")
    else:
        flash("Vehicle details updated successfully.", "success")
    return redirect(url_for("customer.vehicles"))


@customer_bp.route("/vehicles/<int:vehicle_id>/delete", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def vehicle_delete(vehicle_id):
    if request.method == "GET":
        return redirect(url_for("customer.vehicles"))
    uid = get_current_user_id()
    ok, err = delete_vehicle(vehicle_id, uid)
    if not ok:
        flash(err, "danger")
    else:
        flash("Vehicle removed from your garage.", "info")
    return redirect(url_for("customer.vehicles"))


@customer_bp.route("/vehicles/<int:vehicle_id>/set-default", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def vehicle_set_default(vehicle_id):
    if request.method == "GET":
        return redirect(url_for("customer.vehicles"))
    uid = get_current_user_id()
    ok, err = set_default_vehicle(uid, vehicle_id)
    if not ok:
        flash(err, "danger")
    else:
        flash("Primary vehicle updated.", "success")
    return redirect(url_for("customer.vehicles"))


# ----------------------------------------------------------------------------
# 4. My Bookings
# ----------------------------------------------------------------------------
@customer_bp.route("/bookings", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def bookings():
    uid = get_current_user_id()
    user_bookings = get_user_bookings(uid)
    paid_booking_ids = {
        r["booking_id"]
        for r in query_all(
            "SELECT DISTINCT booking_id FROM Payments WHERE booking_id IS NOT NULL AND payment_status IN ('SUCCESS', 'CAPTURED')"
        )
    }
    for b in user_bookings:
        # Attach QR token and payment state
        qr = get_or_create_booking_qr(b["booking_id"])
        b["qr_token"] = qr.get("qr_token") if qr else None
        b["is_paid"] = b["booking_id"] in paid_booking_ids
    return render_template("customer/bookings.html", bookings=user_bookings)


@customer_bp.route("/bookings/<int:booking_id>/checkout", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def booking_checkout(booking_id):
    uid = get_current_user_id()
    ctx, err = get_booking_checkout_context(booking_id, uid)
    if err:
        if "Permission denied" in str(err):
            abort(403)
        flash(err, "danger")
        return redirect(url_for("customer.bookings"))

    if ctx.get("is_paid"):
        flash("This booking reservation is already settled.", "info")
        return redirect(url_for("customer.payment_result", payment_id=ctx["payment"]["payment_id"]))

    creds = get_razorpay_credentials()
    return render_template(
        "customer/checkout.html",
        ctx=ctx,
        is_booking=True,
        booking_id=booking_id,
        key_id=creds.get("key_id", ""),
        has_secret=bool(creds.get("key_secret")),
    )


@customer_bp.route("/book/<int:point_id>", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def book_slot(point_id):
    uid = get_current_user_id()
    point = get_point_by_id(point_id)
    if not point:
        flash("Charging dispenser not found.", "danger")
        return redirect(url_for("customer.stations"))

    station = get_station_by_id(point["station_id"])
    vehicles = get_vehicles_by_user(uid)
    if not vehicles:
        flash("Please register an EV in My Vehicles before reserving a charging slot.", "warning")
        return redirect(url_for("customer.vehicles"))

    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        start_time_str = request.form.get("start_time")
        duration_minutes = int(request.form.get("duration_minutes", 60))

        if not vehicle_id or not start_time_str:
            flash("Please choose your vehicle and reservation start time.", "danger")
            return render_template("customer/book.html", point=point, station=station, vehicles=vehicles)

        try:
            start_dt = datetime.fromisoformat(start_time_str.replace("T", " "))
            end_dt = start_dt + timedelta(minutes=duration_minutes)
        except ValueError:
            flash("Invalid date or time format.", "danger")
            return render_template("customer/book.html", point=point, station=station, vehicles=vehicles)

        if start_dt < datetime.now() - timedelta(minutes=5):
            flash("Reservation start time cannot be in the past.", "danger")
            return render_template("customer/book.html", point=point, station=station, vehicles=vehicles)

        bid, err = create_booking(uid, vehicle_id, point_id, start_dt, end_dt)
        if err:
            flash(err, "danger")
            return render_template("customer/book.html", point=point, station=station, vehicles=vehicles)

        flash(f"Slot reserved successfully! Booking reference #{bid}.", "success")
        return redirect(url_for("customer.bookings"))

    # Pre-select default vehicle if any
    default_vid = next((v["vehicle_id"] for v in vehicles if v.get("is_default")), vehicles[0]["vehicle_id"])
    now_slot = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
    return render_template(
        "customer/book.html",
        point=point,
        station=station,
        vehicles=vehicles,
        default_vid=default_vid,
        default_start=now_slot,
    )


@customer_bp.route("/bookings/<int:booking_id>/cancel", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def booking_cancel(booking_id):
    if request.method == "GET":
        return redirect(url_for("customer.bookings"))
    uid = get_current_user_id()
    ok, err = cancel_booking(booking_id, uid)
    if not ok:
        flash(err, "danger")
    else:
        flash(f"Booking #{booking_id} has been cancelled.", "info")
    return redirect(url_for("customer.bookings"))


@customer_bp.route("/bookings/<int:booking_id>/qr.png", methods=["GET"])
@login_required
def booking_qr_png(booking_id):
    uid = get_current_user_id()
    b = query_one("SELECT booking_id, user_id FROM Bookings WHERE booking_id = %s", (booking_id,))
    if not b:
        abort(404)
    if b["user_id"] != uid and normalize_role(session.get("role")) != "ADMIN":
        abort(403)
    qr_row = get_or_create_booking_qr(booking_id)
    if not qr_row:
        abort(404)
    img_bytes = render_qr_png_bytes(qr_row["qr_token"])
    return Response(img_bytes, mimetype="image/png")


# ----------------------------------------------------------------------------
# 5. Active Charging Sessions (Simulator & Live Monitor)
# ----------------------------------------------------------------------------
@customer_bp.route("/charging", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def charging():
    uid = get_current_user_id()
    active_session = get_active_session_for_user(uid)
    available_points = query_all(
        "SELECT cp.*, s.station_name, s.city "
        "FROM ChargingPoints cp "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE cp.point_status = 'AVAILABLE' AND s.station_status = 'ACTIVE' "
        "ORDER BY s.station_name ASC LIMIT 20"
    )
    user_vehicles = get_vehicles_by_user(uid)
    return render_template(
        "customer/charging.html",
        active_session=active_session,
        available_points=available_points,
        vehicles=user_vehicles,
    )


@customer_bp.route("/charging/start", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def charging_start():
    if request.method == "GET":
        return redirect(url_for("customer.charging"))
    uid = get_current_user_id()
    existing = get_active_session_for_user(uid)
    if existing:
        flash("You already have an active charging session in progress.", "warning")
        return redirect(url_for("customer.charging"))

    vehicle_id = request.form.get("vehicle_id")
    point_id = request.form.get("point_id")
    booking_id = request.form.get("booking_id")

    if not vehicle_id or not point_id:
        flash("Please select both a vehicle and an available charging dispenser.", "danger")
        return redirect(url_for("customer.charging"))

    sid, err = start_session(uid, vehicle_id, point_id, booking_id=booking_id)
    if err:
        flash(err, "danger")
    else:
        flash(f"Charging session #{sid} initiated! Dispenser is delivering power.", "success")
    return redirect(url_for("customer.charging"))


@customer_bp.route("/charging/stop/<int:session_id>", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def charging_stop(session_id):
    if request.method == "GET":
        return redirect(url_for("customer.charging"))
    uid = get_current_user_id()
    final_soc = float(request.form.get("final_soc", 80.0))
    energy_kwh = float(request.form.get("energy_consumed_kwh", 15.5))

    ok, err = complete_session(session_id, energy_kwh=energy_kwh, user_id=uid)
    if not ok:
        flash(err, "danger")
        return redirect(url_for("customer.charging"))

    flash("Charging complete! Please proceed to settle payment.", "success")
    return redirect(url_for("customer.checkout", session_id=session_id))


# ----------------------------------------------------------------------------
# 6. Charging History & CSV Export
# ----------------------------------------------------------------------------
@customer_bp.route("/history", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def history():
    uid = get_current_user_id()
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search = request.args.get("search")
    sort = request.args.get("sort", "desc")
    page = max(1, int(request.args.get("page", 1)))

    rows, total_count, total_pages, current_p = get_customer_charging_history(
        uid, start_date=start_date, end_date=end_date, search=search, sort=sort, page=page, per_page=10
    )
    return render_template(
        "customer/history.html",
        sessions=rows,
        total_count=total_count,
        total_pages=total_pages,
        current_page=current_p,
        start_date=start_date,
        end_date=end_date,
        search=search,
        sort=sort,
    )


@customer_bp.route("/history/export", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def history_export():
    uid = get_current_user_id()
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search = request.args.get("search")
    csv_data = generate_customer_history_csv(uid, start_date=start_date, end_date=end_date, search=search)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=chargenet_sessions_{stamp}.csv"},
    )


# ----------------------------------------------------------------------------
# 7. Payments & Booking (Reserve & Pay Wizard + Transaction Ledger)
# ----------------------------------------------------------------------------
@customer_bp.route("/payments", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def payments():
    uid = get_current_user_id()
    search = (request.args.get("search") or request.args.get("q") or "").strip()
    status = request.args.get("status", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    page = request.args.get("page", 1)

    # Tab selection: 'reserve' (Wizard) vs 'ledger' (Transactions)
    active_tab = request.args.get("tab", "").strip().lower()
    pre_station_id = request.args.get("station_id", type=int)
    pre_point_id = request.args.get("point_id", type=int)
    if not active_tab:
        active_tab = "reserve" if (pre_station_id or pre_point_id) else "ledger"

    payment_list, total_count, total_pages, current_page = get_customer_payments(
        uid, search=search, status=status, start_date=start_date, end_date=end_date, page=page, per_page=15
    )
    summary = get_customer_payment_summary(uid)

    # Data for the Reserve & Pay 5-step wizard
    reserve_stations = get_all_stations(status="ACTIVE")
    user_vehicles = get_vehicles_by_user(uid)
    available_points = query_all(
        "SELECT cp.*, s.station_name, s.city, s.address, s.operator_name "
        "FROM ChargingPoints cp "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE cp.point_status = 'AVAILABLE' AND s.station_status = 'ACTIVE' "
        "ORDER BY s.station_name, cp.point_code"
    )

    return render_template(
        "customer/payments.html",
        active_tab=active_tab,
        payments=payment_list,
        summary=summary,
        total_count=total_count,
        total_pages=total_pages,
        current_page=current_page,
        selected_status=status,
        search_query=search,
        start_date=start_date,
        end_date=end_date,
        reserve_stations=reserve_stations,
        user_vehicles=user_vehicles,
        available_points=available_points,
        pre_station_id=pre_station_id,
        pre_point_id=pre_point_id,
    )


@customer_bp.route("/reserve-and-pay", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def reserve_and_pay():
    """Process 5-step customer booking submission: supports Online (Razorpay) and Offline (Cash at Station)."""
    if request.method == "GET":
        return redirect(url_for("customer.payments", tab="reserve"))
    import uuid
    uid = get_current_user_id()
    point_id = request.form.get("point_id", type=int)
    vehicle_id = request.form.get("vehicle_id", type=int)
    start_at_raw = (request.form.get("start_at") or request.form.get("start_time") or "").strip()
    duration_val = request.form.get("duration_hours")
    if duration_val:
        duration_hours = float(duration_val)
    elif request.form.get("duration_minutes"):
        duration_hours = float(request.form.get("duration_minutes")) / 60.0
    else:
        duration_hours = 1.0
    estimated_kwh = float(request.form.get("estimated_kwh", 20.0))
    payment_method = request.form.get("payment_method", "ONLINE").strip().upper()

    if not point_id or not vehicle_id:
        flash("Please select both an eligible charging dispenser and your registered EV.", "danger")
        return redirect(url_for("customer.payments", tab="reserve"))

    veh = query_one(
        "SELECT vehicle_id, make, model, registration_no, connector_type FROM Vehicles WHERE vehicle_id = %s AND user_id = %s",
        (vehicle_id, uid)
    )
    if not veh:
        flash("Selected vehicle does not belong to your account.", "danger")
        return redirect(url_for("customer.payments", tab="reserve"))

    if start_at_raw:
        try:
            start_dt = datetime.fromisoformat(start_at_raw.replace("T", " "))
        except ValueError:
            start_dt = datetime.now() + timedelta(minutes=15)
    else:
        start_dt = datetime.now() + timedelta(minutes=15)

    end_dt = start_dt + timedelta(hours=duration_hours)

    booking_id, err = create_booking(uid, vehicle_id, point_id, start_dt, end_dt)
    if err:
        flash(f"Slot reservation failed: {err}", "danger")
        return redirect(url_for("customer.payments", tab="reserve", point_id=point_id))

    point = query_one(
        "SELECT cp.*, s.station_name, s.city, s.address "
        "FROM ChargingPoints cp "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE cp.point_id = %s",
        (point_id,)
    )
    tariff = float(point.get("tariff_per_kwh") or 18.0)
    base_amt = round(tariff * estimated_kwh, 2)
    tax_amt = round(base_amt * 0.18, 2)
    total_amt = round(base_amt + tax_amt, 2)

    if payment_method == "CASH":
        txn_ref = f"TXN-CSH-{uuid.uuid4().hex[:8].upper()}"
        execute(
            "INSERT INTO Payments (booking_id, transaction_reference, amount, base_amount, tax_amount, "
            "                      currency, payment_method, gateway_provider, payment_status, is_simulated, "
            "                      simulation_note) "
            "VALUES (%s, %s, %s, %s, %s, 'INR', 'CASH', 'DEMO_LEDGER', 'PAYMENT_DUE', 1, "
            "        'Offline cash reservation awaiting station attendant receipt')",
            (booking_id, txn_ref, total_amt, base_amt, tax_amt)
        )
        execute(
            "UPDATE Bookings SET booking_status = 'PENDING_PAYMENT', estimated_cost = %s, estimated_energy_kwh = %s WHERE booking_id = %s",
            (total_amt, estimated_kwh, booking_id)
        )
        try:
            add_notification(
                user_id=uid,
                title="Slot Reserved — Cash Payment Due at Station",
                message=f"Reserved dispenser {point['point_code']} at {point['station_name']} (#{booking_id}). Amount payable at counter: ₹{total_amt:.2f}.",
                category="BOOKING",
                link_url=f"/customer/payments?tab=ledger",
            )
        except Exception:
            pass

        flash(
            f"Bay {point['point_code']} at {point['station_name']} reserved successfully! "
            f"Booking ref #{booking_id}. Payment method: Cash at Station (Status: PAYMENT DUE, Amount: ₹{total_amt:.2f}).",
            "success"
        )
        return redirect(url_for("customer.payments", tab="ledger"))
    else:
        execute(
            "UPDATE Bookings SET estimated_cost = %s, estimated_energy_kwh = %s WHERE booking_id = %s",
            (total_amt, estimated_kwh, booking_id)
        )
        flash(f"Slot reserved at {point['station_name']}! Please complete payment confirmation.", "info")
        return redirect(url_for("customer.booking_checkout", booking_id=booking_id))


@customer_bp.route("/checkout/<int:session_id>", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def checkout(session_id):
    uid = get_current_user_id()
    ctx, err = get_checkout_context(session_id, uid)
    if err:
        flash(err, "danger")
        return redirect(url_for("customer.dashboard"))

    # If already paid, redirect straight to payment result
    if ctx.get("is_paid"):
        return redirect(url_for("customer.payment_result", payment_id=ctx["payment"]["payment_id"]))

    creds = get_razorpay_credentials()
    return render_template(
        "customer/checkout.html",
        ctx=ctx,
        key_id=creds.get("key_id", ""),
        has_secret=bool(creds.get("key_secret")),
    )


@customer_bp.route("/payment-result/<int:payment_id>", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def payment_result(payment_id):
    uid = get_current_user_id()
    payment = query_one(
        "SELECT p.*, "
        "       COALESCE(cs.energy_kwh, 0) AS energy_consumed_kwh, "
        "       COALESCE(cs.energy_kwh, 0) AS energy_kwh, "
        "       COALESCE(cs.start_at, p.created_at) AS start_time, "
        "       COALESCE(cs.start_at, p.created_at) AS start_at, "
        "       COALESCE(cs.end_at, p.paid_at) AS end_time, "
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
        "WHERE p.payment_id = %s AND (cs.user_id = %s OR b.user_id = %s)",
        (payment_id, uid, uid)
    )
    if not payment:
        flash("Payment receipt not found.", "danger")
        return redirect(url_for("customer.payments"))

    return render_template("customer/payment_result.html", payment=payment)


@customer_bp.route("/payments/<int:payment_id>/receipt", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def payment_receipt_text(payment_id):
    """Download plain text tax invoice & charge receipt with strict ownership enforcement."""
    uid = get_current_user_id()
    p_exists = query_one("SELECT payment_id FROM Payments WHERE payment_id = %s", (payment_id,))
    if not p_exists:
        abort(404)

    payment = query_one(
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
        "WHERE p.payment_id = %s AND (cs.user_id = %s OR b.user_id = %s)",
        (payment_id, uid, uid)
    )
    if not payment:
        abort(403)

    text_receipt = (
        "============================================================\n"
        "        EZ CHARGE NETWORK — TAX INVOICE & CHARGE RECEIPT   \n"
        "============================================================\n"
        f"Invoice / Payment ID : #{payment['payment_id']}\n"
        f"Transaction Ref      : {payment.get('transaction_reference', 'N/A')}\n"
        f"Gateway Provider     : {payment.get('gateway_provider', 'RAZORPAY_TEST')}\n"
        f"Station Name         : {payment.get('station_name')}\n"
        f"Location             : {payment.get('city')}, {payment.get('address')}\n"
        f"Dispenser & Plug     : {payment.get('point_code')} ({payment.get('connector_type')})\n"
        f"Vehicle              : {payment.get('make')} {payment.get('model')} ({payment.get('registration_no')})\n"
        f"Payment Status       : {payment.get('payment_status')}\n"
        f"Date & Time          : {payment.get('paid_at') or payment.get('created_at')}\n"
        "------------------------------------------------------------\n"
        f"Base Amount          : ₹{float(payment.get('base_amount') or 0):.2f}\n"
        f"GST (18% Included)   : ₹{float(payment.get('tax_amount') or 0):.2f}\n"
        f"TOTAL SETTLED        : ₹{float(payment.get('amount') or 0):.2f}\n"
        "============================================================\n"
        "  Academic Demonstration — Tata Power EZ Charge Reference\n"
        "============================================================\n"
    )
    return Response(
        text_receipt,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=receipt_invoice_{payment_id}.txt"},
    )


@customer_bp.route("/session/<int:session_id>", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def session_detail(session_id):
    uid = get_current_user_id()
    receipt = get_session_receipt(session_id, user_id=uid)
    if not receipt:
        flash("Charging session receipt not found or access denied.", "danger")
        return redirect(url_for("customer.history"))
    return render_template("customer/session_detail.html", receipt=receipt)


@customer_bp.route("/session/<int:session_id>/download", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def session_download_receipt(session_id):
    uid = get_current_user_id()
    receipt = get_session_receipt(session_id, user_id=uid)
    if not receipt:
        flash("Charging session receipt not found or access denied.", "danger")
        return redirect(url_for("customer.history"))

    text_receipt = (
        "============================================================\n"
        "              EV CHARGENET — CHARGING RECEIPT\n"
        "============================================================\n"
        f"Receipt / Session ID : #{receipt.get('session_id')}\n"
        f"Station Name         : {receipt.get('station_name')}\n"
        f"Location             : {receipt.get('station_city') or receipt.get('city')}, {receipt.get('station_address') or receipt.get('address')}\n"
        f"Dispenser Code       : {receipt.get('point_code')} ({receipt.get('connector_type')})\n"
        f"Vehicle              : {receipt.get('make')} {receipt.get('model')} ({receipt.get('registration_no')})\n"
        f"Start Time           : {receipt.get('start_at') or receipt.get('start_time')}\n"
        f"End Time             : {receipt.get('end_at') or receipt.get('end_time')}\n"
        f"Energy Delivered     : {receipt.get('energy_kwh') or receipt.get('energy_consumed_kwh') or 0} kWh\n"
        f"Tariff Rate          : ₹{receipt.get('tariff_per_kwh') or receipt.get('rate_per_kwh') or 0} / kWh\n"
        "------------------------------------------------------------\n"
        f"TOTAL AMOUNT PAID    : ₹{float(receipt.get('total_amount') or receipt.get('total_cost') or 0):.2f}\n"
        f"Payment Status       : {receipt.get('payment_status', 'PAID')}\n"
        f"Transaction Ref      : {receipt.get('transaction_reference', 'N/A')}\n"
        "============================================================\n"
        "  Thank you for charging with EZ Charge Network Portal!\n"
        "============================================================\n"
    )
    return Response(
        text_receipt,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=receipt_{session_id}.txt"},
    )


# ----------------------------------------------------------------------------
# 8. QR Scanner (Interactive Camera + Manual Code Resolver)
# ----------------------------------------------------------------------------
@customer_bp.route("/qr-scanner", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def qr_scanner():
    return render_template("customer/qr_scanner.html")


# ----------------------------------------------------------------------------
# 9. Saved Stations (Bookmarks)
# ----------------------------------------------------------------------------
@customer_bp.route("/saved-stations", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def saved_stations():
    uid = get_current_user_id()
    saved_list = get_saved_stations_for_user(uid)
    return render_template("customer/saved_stations.html", saved_stations=saved_list)


@customer_bp.route("/saved-stations/<int:station_id>/toggle", methods=["POST"])
@login_required
@role_required("CUSTOMER")
def saved_station_toggle(station_id):
    uid = get_current_user_id()
    saved, msg = toggle_saved_station(uid, station_id)
    if request.is_json:
        return jsonify({"success": True, "saved": saved, "message": msg})
    flash(msg, "success" if saved else "info")
    return redirect(request.referrer or url_for("customer.saved_stations"))


# ----------------------------------------------------------------------------
# 10. Notifications
# ----------------------------------------------------------------------------
@customer_bp.route("/notifications", methods=["GET"])
@login_required
@role_required("CUSTOMER")
def notifications():
    uid = get_current_user_id()
    notifs = get_customer_notifications(uid, limit=50)
    return render_template("customer/notifications.html", notifications=notifs)


@customer_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
@role_required("CUSTOMER")
def notification_read(notification_id):
    uid = get_current_user_id()
    mark_notification_read(notification_id, uid)
    if request.is_json:
        return jsonify({"success": True})
    return redirect(url_for("customer.notifications"))


@customer_bp.route("/notifications/mark-all-read", methods=["POST"])
@login_required
@role_required("CUSTOMER")
def notifications_mark_all_read():
    uid = get_current_user_id()
    mark_all_notifications_read(uid)
    flash("All notifications marked as read.", "info")
    return redirect(url_for("customer.notifications"))


# ----------------------------------------------------------------------------
# 11. My Profile
# ----------------------------------------------------------------------------
@customer_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def profile():
    uid = get_current_user_id()
    user = get_user_profile(uid)
    if not user:
        flash("Profile not found.", "danger")
        return redirect(url_for("customer.dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        avatar_url = None
        upload = request.files.get("profile_picture")
        if upload and upload.filename:
            avatar_url, upload_err = save_uploaded_avatar(upload, current_app.static_folder)
            if upload_err:
                flash(upload_err, "danger")
                return render_template("customer/profile.html", user=user)
        else:
            raw_url = (request.form.get("profile_picture_url") or "").strip()
            if raw_url and raw_url.startswith(("https://", "http://")):
                avatar_url = raw_url[:500]

        if new_password:
            if new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                return render_template("customer/profile.html", user=user)

        ok, err = update_user_profile(
            user_id=uid,
            full_name=full_name,
            phone=phone,
            current_password=current_password if new_password else None,
            new_password=new_password if new_password else None,
            profile_picture_url=avatar_url,
        )
        if not ok:
            flash(err, "danger")
            return render_template("customer/profile.html", user=user)

        session["full_name"] = full_name
        if avatar_url:
            session["profile_picture_url"] = avatar_url

        flash("Your profile was updated successfully.", "success")
        return redirect(url_for("customer.profile"))

    return render_template("customer/profile.html", user=user)


# ----------------------------------------------------------------------------
# 12. Help & Support (Web3Forms + Support History)
# ----------------------------------------------------------------------------
@customer_bp.route("/support", methods=["GET", "POST"])
@login_required
@role_required("CUSTOMER")
def support():
    uid = get_current_user_id()
    user = get_user_profile(uid) or {
        "user_id": uid,
        "full_name": session.get("full_name", "Customer"),
        "email": session.get("email", ""),
        "phone": None,
    }
    categories = get_support_categories()

    if request.method == "POST":
        category_input = request.form.get("category", "GENERAL").strip()
        category = categories.get(category_input, category_input)
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        contact_id, delivered, feedback_msg, is_val_err = submit_contact_enquiry(
            full_name=user.get("full_name", "Customer"),
            email=user.get("email", ""),
            phone=user.get("phone"),
            subject=f"[{category}] {subject}" if not subject.startswith("[") else subject,
            message=message,
            category=category,
            ip_address=request.remote_addr,
        )
        if is_val_err or not contact_id:
            flash(feedback_msg or "Failed to submit support ticket. Please check your inputs.", "danger")
        else:
            ticket_ref = f"TKT-{contact_id:05d}"
            flash(f"Support ticket #{ticket_ref} created successfully! Our operations desk has been notified.", "success")
            return redirect(url_for("customer.support"))

    # Safely fetch customer's previous tickets with database error resilience
    past_tickets = []
    try:
        user_email = user.get("email") if user else None
        if user_email:
            past_tickets = query_all(
                "SELECT id, ticket_reference, full_name, email, subject, category, message, "
                "       submission_status, admin_response, created_at, updated_at "
                "FROM ContactMessages WHERE email = %s ORDER BY created_at DESC LIMIT 15",
                (user_email,)
            ) or []
    except Exception as exc:
        current_app.logger.error(f"Support ticket retrieval failed for UID {uid}: {exc}")
        past_tickets = []

    return render_template(
        "customer/support.html",
        user=user,
        categories=categories,
        past_tickets=past_tickets,
    )
