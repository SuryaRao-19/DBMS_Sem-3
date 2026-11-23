"""
Admin / Station Operator Routes
EV Charging Station Management System - DBMS Capstone Project
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, abort
from app.routes.auth_middleware import login_required, role_required, get_current_user_id
from app.services.station_service import (
    get_all_stations, get_station_by_id, create_station, update_station,
    get_all_charging_points, create_charging_point, update_charging_point, get_point_by_id
)
from app.services.booking_service import get_all_bookings
from app.services.session_service import get_all_sessions
from app.services.payment_service import get_all_payments
from app.services.auth_service import get_all_users, toggle_user_status, create_user_by_admin
from app.services.report_service import (
    get_admin_dashboard_metrics, get_monthly_revenue_report,
    get_monthly_energy_report, get_station_utilization_report,
    get_booking_status_distribution, get_system_health,
    get_admin_chart_analytics,
)
from app.services.audit_service import (
    log_audit_event, get_audit_logs, get_system_settings_list, update_system_setting
)
from app.services.contact_service import (
    get_contact_messages, update_contact_status, VALID_ENQUIRY_STATUSES
)
from app.services.station_import_service import (
    import_stations_from_csv, review_station_approval, get_pending_approval_stations
)
from app.services.platform_service import (
    get_data_sources, update_data_source, VALID_DATA_STATUSES
)
from app.services.openchargemap_service import sync_openchargemap_stations
from app.services.api_health_service import get_api_integration_overview
from app.services.qr_service import (
    get_or_create_station_qr,
    regenerate_station_qr,
    revoke_station_qr,
    render_qr_png_bytes,
    render_qr_svg_bytes,
    get_or_create_point_qr,
    regenerate_point_qr,
)
from app.services.customer_service import add_notification
from app.db import query_all, query_one, execute

admin_bp = Blueprint("admin", __name__)



@admin_bp.before_request
@login_required
@role_required("ADMIN")
def enforce_admin_access():
    pass


@admin_bp.route("/dashboard")
def dashboard():
    metrics = get_admin_dashboard_metrics()
    recent_bookings = get_all_bookings()[:5]
    recent_sessions = get_all_sessions()[:5]
    charts = get_admin_chart_analytics()
    api_overview = get_api_integration_overview()
    return render_template(
        "admin/dashboard.html",
        metrics=metrics,
        recent_bookings=recent_bookings,
        recent_sessions=recent_sessions,
        charts=charts,
        api_overview=api_overview,
    )


@admin_bp.route("/stations", methods=["GET", "POST"])
def stations():
    if request.method == "POST":
        station_name = request.form.get("station_name")
        address = request.form.get("address")
        city = request.form.get("city")
        state = request.form.get("state", "Delhi NCR")
        postal_code = request.form.get("postal_code")
        opening_time = request.form.get("opening_time", "06:00:00")
        closing_time = request.form.get("closing_time", "23:00:00")
        status = request.form.get("station_status", "ACTIVE")
        operator_name = request.form.get("operator_name", "Tata Power EZ Charge")
        verif_status = request.form.get("verification_status", "DEMO")
        lat_raw = request.form.get("latitude", "").strip()
        lng_raw = request.form.get("longitude", "").strip()
        source_url = request.form.get("source_url", "").strip() or None

        try:
            lat = float(lat_raw) if lat_raw else None
            lng = float(lng_raw) if lng_raw else None
        except ValueError:
            flash("Invalid latitude or longitude format.", "danger")
            return redirect(url_for("admin.stations"))

        if not station_name or not address or not city:
            flash("Station name, address, and city are required.", "danger")
        else:
            sid = create_station(
                station_name, address, city, opening_time, closing_time, status,
                state=state, postal_code=postal_code, latitude=lat, longitude=lng,
                operator_name=operator_name, source_url=source_url,
                verification_status=verif_status, approval_status="APPROVED",
            )
            log_audit_event(
                action="CREATE_STATION",
                entity_name="Stations",
                entity_id=sid,
                user_id=get_current_user_id(),
                details=f"Created station '{station_name}' in {city} (Status: {status})",
                ip_address=request.remote_addr
            )
            flash(f"Charging Station '{station_name}' created successfully.", "success")
        return redirect(url_for("admin.stations"))

    city_filter = request.args.get("city")
    status_filter = request.args.get("status")
    all_stations = get_all_stations(city=city_filter, status=status_filter, only_approved=False)
    pending_stations = get_pending_approval_stations()
    return render_template("admin/stations.html", stations=all_stations, pending_stations=pending_stations)


@admin_bp.route("/stations/<int:station_id>/edit", methods=["POST"])
def edit_station(station_id):
    if not get_station_by_id(station_id, only_approved=False):
        flash("Charging station not found.", "danger")
        return redirect(url_for("admin.stations")), 404

    station_name = request.form.get("station_name")
    address = request.form.get("address")
    city = request.form.get("city")
    opening_time = request.form.get("opening_time")
    closing_time = request.form.get("closing_time")
    status = request.form.get("station_status")

    update_station(station_id, station_name, address, city, opening_time, closing_time, status)
    log_audit_event(
        action="UPDATE_STATION",
        entity_name="Stations",
        entity_id=station_id,
        user_id=get_current_user_id(),
        details=f"Updated station {station_id} status to {status}",
        ip_address=request.remote_addr
    )
    flash("Station updated successfully.", "success")
    return redirect(url_for("admin.stations"))


@admin_bp.route("/stations/import", methods=["POST"])
def import_stations():
    """Import charging stations from CSV file or pasted CSV data into pending review queue."""
    csv_text = request.form.get("csv_text", "").strip()
    uploaded = request.files.get("csv_file")
    if uploaded and uploaded.filename:
        csv_text = uploaded.read().decode("utf-8", errors="ignore")

    approve_now = request.form.get("approve_immediately") == "1"
    result = import_stations_from_csv(csv_text, approve_immediately=approve_now)

    admin_id = get_current_user_id()
    log_audit_event(
        action="IMPORT_STATIONS_CSV",
        entity_name="Stations",
        entity_id=None,
        user_id=admin_id,
        details=f"CSV import: {len(result['imported_ids'])} imported, {len(result['skipped'])} duplicates skipped, {len(result['errors'])} errors",
        ip_address=request.remote_addr,
    )

    if result["imported_ids"]:
        state_msg = "published immediately" if approve_now else "queued for admin approval"
        flash(f"Imported {len(result['imported_ids'])} station(s) ({state_msg}).", "success")
    if result["skipped"]:
        flash(f"Skipped {len(result['skipped'])} duplicate(s): {'; '.join(result['skipped'][:3])}", "warning")
    if result["errors"]:
        flash(f"Validation rejected {len(result['errors'])} row(s): {'; '.join(result['errors'][:3])}", "danger")

    return redirect(url_for("admin.stations"))


@admin_bp.route("/stations/sync-ocm", methods=["POST"], endpoint="sync_ocm")
@admin_bp.route("/sync-ocm-stations", methods=["POST"], endpoint="sync_ocm_stations_route")
@admin_bp.route("/integrations/ocm/sync", methods=["POST"])
def sync_ocm():
    """Trigger synchronization of Open Charge Map POI records for Delhi NCR."""
    admin_id = get_current_user_id()
    city = request.form.get("city", "Delhi NCR").strip()
    try:
        max_res = min(50, max(5, int(request.form.get("max_results", 25))))
    except (TypeError, ValueError):
        max_res = 25

    coords = {
        "Delhi NCR": (28.6139, 77.2090),
        "Gurugram": (28.4595, 77.0266),
        "Noida": (28.5355, 77.3910),
        "Faridabad": (28.4089, 77.3178),
        "Ghaziabad": (28.6692, 77.4538),
    }
    lat, lng = coords.get(city, (28.6139, 77.2090))

    res = sync_openchargemap_stations(latitude=lat, longitude=lng, distance_km=45, max_results=max_res)

    log_audit_event(
        action="SYNC_OPEN_CHARGE_MAP",
        entity_name="Stations",
        entity_id=None,
        user_id=admin_id,
        details=f"OCM sync for {city}: {res.get('imported', 0)} imported, {res.get('updated', 0)} updated, {res.get('duplicates', 0)} duplicates",
        ip_address=request.remote_addr,
    )

    if res.get("success"):
        flash(
            f"Open Charge Map Sync Complete ({city}): {res.get('imported', 0)} new stations imported, "
            f"{res.get('updated', 0)} updated, {res.get('duplicates', 0)} duplicates checked.",
            "success"
        )
    else:
        flash(f"Open Charge Map synchronization note: {res.get('message', 'Completed with cached data')}", "info")

    next_endpoint = request.form.get("next_endpoint")
    if next_endpoint == "admin.dashboard":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("admin.stations"))


@admin_bp.route("/stations/<int:station_id>/qr/png", endpoint="download_qr_png")
@admin_bp.route("/stations/<int:station_id>/qr.png", endpoint="station_qr_png")
def station_qr_png(station_id):
    qr = get_or_create_station_qr(station_id, admin_user_id=get_current_user_id())
    if not qr:
        abort(404)
    target_url = url_for("public.scan_station_qr", token=qr["qr_token"], _external=True)
    img = render_qr_png_bytes(target_url)
    return Response(img, mimetype="image/png")


@admin_bp.route("/stations/<int:station_id>/qr/svg", endpoint="download_qr_svg")
@admin_bp.route("/stations/<int:station_id>/qr.svg", endpoint="station_qr_svg")
def station_qr_svg(station_id):
    qr = get_or_create_station_qr(station_id, admin_user_id=get_current_user_id())
    if not qr:
        abort(404)
    target_url = url_for("public.scan_station_qr", token=qr["qr_token"], _external=True)
    svg = render_qr_svg_bytes(target_url)
    return Response(svg, mimetype="image/svg+xml")


@admin_bp.route("/stations/<int:station_id>/qr/print", endpoint="print_station_qr")
def station_qr_print(station_id):
    station = get_station_by_id(station_id)
    if not station:
        flash("Station not found.", "danger")
        return redirect(url_for("admin.stations")), 404
    qr = get_or_create_station_qr(station_id, admin_user_id=get_current_user_id())
    return render_template("admin/print_qr.html", station=station, qr=qr, qr_row=qr)


@admin_bp.route("/stations/<int:station_id>/qr/regenerate", methods=["POST"], endpoint="regenerate_qr_route")
def station_qr_regenerate(station_id):
    admin_id = get_current_user_id()
    new_qr, err = regenerate_station_qr(station_id, admin_id)
    if err:
        flash(err, "danger")
    else:
        flash("Station QR token rotated successfully.", "success")
    return redirect(url_for("admin.stations"))


@admin_bp.route("/stations/<int:station_id>/qr/revoke", methods=["POST"], endpoint="revoke_qr_route")
def station_qr_revoke(station_id):
    admin_id = get_current_user_id()
    ok, err = revoke_station_qr(station_id, admin_id)
    if not ok:
        flash(err, "danger")
    else:
        flash("Station QR token revoked.", "info")
    return redirect(url_for("admin.stations"))


@admin_bp.route("/points/<int:point_id>/qr.png", endpoint="download_point_qr_png")
@admin_bp.route("/points/<int:point_id>/qr/png", endpoint="point_qr_png")
def point_qr_png(point_id):
    qr = get_or_create_point_qr(point_id, created_by=get_current_user_id())
    if not qr:
        abort(404)
    target_url = url_for("public.scan_point_qr", token=qr["qr_token"], _external=True)
    img = render_qr_png_bytes(target_url)
    return Response(img, mimetype="image/png")


@admin_bp.route("/points/<int:point_id>/qr/regenerate", methods=["POST"], endpoint="regenerate_point_qr_route")
def point_qr_regenerate(point_id):
    admin_id = get_current_user_id()
    token = regenerate_point_qr(point_id, created_by=admin_id)
    flash("Point QR token rotated successfully.", "success")
    return redirect(url_for("admin.points"))


@admin_bp.route("/stations/<int:station_id>/review", methods=["POST"])
@admin_bp.route("/stations/<int:station_id>/verify", methods=["POST"], endpoint="verify_station_route")
def review_station(station_id):
    """Approve or reject imported/unverified charging stations or update verification status."""
    decision = request.form.get("decision", "").strip().upper()
    verif_status = request.form.get("verification_status", "").strip().upper() or None
    if decision:
        success, msg = review_station_approval(station_id, decision, verification_status=verif_status)
    elif verif_status:
        execute(
            "UPDATE Stations SET verification_status = %s, last_verified_at = NOW() WHERE station_id = %s",
            (verif_status, station_id),
        )
        msg = f"Station #{station_id} verification status updated to {verif_status}."
        success = True
    else:
        success, msg = False, "No decision or verification status provided."

    if success:
        log_audit_event(
            action="REVIEW_STATION_APPROVAL",
            entity_name="Stations",
            entity_id=station_id,
            user_id=get_current_user_id(),
            details=msg,
            ip_address=request.remote_addr,
        )
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.stations"))


@admin_bp.route("/points", methods=["GET", "POST"])
def points():
    if request.method == "POST":
        station_id = request.form.get("station_id")
        point_code = request.form.get("point_code")
        connector_type = request.form.get("connector_type")
        max_power_kw = request.form.get("max_power_kw")
        tariff_per_kwh = request.form.get("tariff_per_kwh")
        point_status = request.form.get("point_status", "AVAILABLE")

        try:
            pid = create_charging_point(station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
            log_audit_event(
                action="CREATE_POINT",
                entity_name="ChargingPoints",
                entity_id=pid,
                user_id=get_current_user_id(),
                details=f"Added dispenser '{point_code}' to station {station_id} ({connector_type}, {max_power_kw}kW, tariff {tariff_per_kwh})",
                ip_address=request.remote_addr
            )
            flash(f"Dispenser '{point_code}' added successfully.", "success")
        except Exception as e:
            flash(f"Error adding charging point: {str(e)}", "danger")
        return redirect(url_for("admin.points"))

    all_points = get_all_charging_points()
    stations_list = get_all_stations()
    return render_template("admin/points.html", points=all_points, stations=stations_list)


@admin_bp.route("/points/<int:point_id>/edit", methods=["POST"])
def edit_point(point_id):
    if not get_point_by_id(point_id):
        flash("Charging point not found.", "danger")
        return redirect(url_for("admin.points")), 404

    point_code = request.form.get("point_code")
    connector_type = request.form.get("connector_type")
    max_power_kw = request.form.get("max_power_kw")
    tariff_per_kwh = request.form.get("tariff_per_kwh")
    point_status = request.form.get("point_status")

    try:
        update_charging_point(point_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
        log_audit_event(
            action="UPDATE_POINT",
            entity_name="ChargingPoints",
            entity_id=point_id,
            user_id=get_current_user_id(),
            details=f"Updated dispenser {point_id} to status {point_status}, tariff {tariff_per_kwh}",
            ip_address=request.remote_addr
        )
        flash(f"Charging point '{point_code}' updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating point: {str(e)}", "danger")
    return redirect(url_for("admin.points"))


@admin_bp.route("/bookings")
def bookings():
    all_bookings = get_all_bookings()
    return render_template("admin/bookings.html", bookings=all_bookings)


@admin_bp.route("/sessions")
def sessions():
    all_sessions = get_all_sessions()
    return render_template("admin/sessions.html", sessions=all_sessions)


@admin_bp.route("/payments")
def payments():
    all_payments = get_all_payments()
    return render_template("admin/payments.html", payments=all_payments)


@admin_bp.route("/payments/<int:payment_id>/collect-cash", methods=["POST"])
def collect_cash_payment(payment_id):
    """Confirm receipt of offline cash payment at station counter / bay."""
    admin_id = get_current_user_id()
    notes = request.form.get("notes", "Cash collected at station counter / bay").strip()

    payment = query_one(
        "SELECT p.*, b.booking_id, b.user_id, s.station_name "
        "FROM Payments p "
        "LEFT JOIN Bookings b ON b.booking_id = p.booking_id "
        "LEFT JOIN ChargingPoints cp ON cp.point_id = b.point_id "
        "LEFT JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE p.payment_id = %s",
        (payment_id,)
    )
    if not payment:
        flash("Payment record not found.", "danger")
        return redirect(url_for("admin.payments"))

    if payment["payment_status"] != "PAYMENT_DUE":
        flash(f"Payment #{payment_id} is in status '{payment['payment_status']}' and cannot be recollected.", "warning")
        return redirect(url_for("admin.payments"))

    execute(
        "UPDATE Payments "
        "SET payment_status = 'SUCCESS', "
        "    paid_at = NOW(), "
        "    cash_collected_by = %s, "
        "    cash_collected_at = NOW(), "
        "    cash_notes = %s "
        "WHERE payment_id = %s",
        (admin_id, notes, payment_id)
    )

    if payment.get("booking_id"):
        execute(
            "UPDATE Bookings SET booking_status = 'CONFIRMED' WHERE booking_id = %s",
            (payment["booking_id"],)
        )

    log_audit_event(
        action="COLLECT_CASH_PAYMENT",
        entity_name="Payments",
        entity_id=payment_id,
        user_id=admin_id,
        details=f"Admin #{admin_id} confirmed cash collection of ₹{payment['amount']} for Payment #{payment_id} (Booking #{payment.get('booking_id')})",
        ip_address=request.remote_addr,
    )

    if payment.get("user_id"):
        try:
            add_notification(
                user_id=payment["user_id"],
                title="Cash Payment Received & Confirmed",
                message=f"Cash payment of ₹{float(payment['amount']):.2f} for booking #{payment.get('booking_id')} was confirmed by station administration.",
                category="PAYMENT",
                link_url=f"/customer/payments",
            )
        except Exception:
            pass

    flash(f"Cash payment of ₹{float(payment['amount']):.2f} (Payment #{payment_id}) recorded successfully. Booking marked CONFIRMED.", "success")
    return redirect(url_for("admin.payments"))


@admin_bp.route("/reports")
def reports():
    revenue_data = get_monthly_revenue_report()
    energy_data = get_monthly_energy_report()
    utilization_data = get_station_utilization_report()
    status_distribution = get_booking_status_distribution()
    return render_template(
        "admin/reports.html",
        revenue_data=revenue_data,
        energy_data=energy_data,
        utilization_data=utilization_data,
        status_distribution=status_distribution
    )


@admin_bp.route("/reports/export")
def export_reports():
    import csv
    import io
    from flask import Response
    from datetime import datetime

    report_type = request.args.get("type", "revenue")
    output = io.StringIO()
    writer = csv.writer(output)

    if report_type == "revenue":
        data = get_monthly_revenue_report()
        writer.writerow(["Station ID", "Station Name", "City", "Billing Month", "Successful Transactions", "Total Revenue (INR)"])
        for r in data:
            writer.writerow([r["station_id"], r["station_name"], r["city"], r["revenue_month"], r["successful_transactions"], r["total_revenue"]])
        filename = f"ev_monthly_revenue_{datetime.now().strftime('%Y%m%d')}.csv"
    elif report_type == "energy":
        data = get_monthly_energy_report()
        writer.writerow(["Station ID", "Station Name", "City", "Usage Month", "Completed Sessions", "Total Energy (kWh)", "Avg kWh / Session"])
        for r in data:
            writer.writerow([r["station_id"], r["station_name"], r["city"], r["usage_month"], r["completed_sessions"], r["total_energy_kwh"], r["avg_kwh_per_session"]])
        filename = f"ev_monthly_energy_{datetime.now().strftime('%Y%m%d')}.csv"
    elif report_type == "utilization":
        data = get_station_utilization_report()
        writer.writerow(["Station ID", "Station Name", "City", "Dispenser Count", "Total Sessions", "Total Charge Hours", "Total kWh Dispensed"])
        for r in data:
            writer.writerow([r["station_id"], r["station_name"], r["city"], r["dispenser_count"], r["total_sessions"], r["total_charge_hours"], r["total_kwh_dispensed"]])
        filename = f"ev_station_utilization_{datetime.now().strftime('%Y%m%d')}.csv"
    elif report_type == "status":
        data = get_booking_status_distribution()
        writer.writerow(["Booking Status", "Total Bookings", "Percentage (%)"])
        for r in data:
            writer.writerow([r["booking_status"], r["count"], r["percentage"]])
        filename = f"ev_booking_distribution_{datetime.now().strftime('%Y%m%d')}.csv"
    else:
        flash("Invalid report export type specified.", "danger")
        return redirect(url_for("admin.reports"))

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )



@admin_bp.route("/users")
def users():
    role_filter = request.args.get("role")
    status_filter = request.args.get("status")
    query = request.args.get("q", "").strip().lower()

    user_list = get_all_users(role=role_filter if role_filter else None, status=status_filter if status_filter else None)

    if query:
        user_list = [
            u for u in user_list
            if query in u["full_name"].lower() or query in u["email"].lower() or (u.get("phone") and query in u["phone"])
        ]

    return render_template(
        "admin/users.html",
        users=user_list,
        selected_role=role_filter,
        selected_status=status_filter,
        search_query=query
    )


@admin_bp.route("/users/create", methods=["POST"])
def create_user():
    """Protected administrative route for provisioning OWNER or ADMIN accounts."""
    full_name = request.form.get("full_name", "")
    email = request.form.get("email", "")
    phone = request.form.get("phone", "")
    password = request.form.get("password", "")
    role = request.form.get("role", "OWNER")

    uid, err = create_user_by_admin(full_name, email, phone, password, role=role)
    if err:
        flash(err, "danger")
    else:
        log_audit_event(
            action="CREATE_USER",
            entity_name="Users",
            entity_id=uid,
            user_id=get_current_user_id(),
            details=f"Admin created account '{email.strip().lower()}' with role {role.strip().upper()}",
            ip_address=request.remote_addr
        )
        flash(f"User account '{email.strip().lower()}' ({role.strip().upper()}) created successfully.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
def toggle_status(user_id):
    current_admin_id = get_current_user_id()
    success, res = toggle_user_status(user_id, current_admin_id)
    if success:
        log_audit_event(
            action="TOGGLE_USER_STATUS",
            entity_name="Users",
            entity_id=user_id,
            user_id=current_admin_id,
            details=f"Admin updated user {user_id} account status to {res}",
            ip_address=request.remote_addr
        )
        flash(f"User account status successfully updated to {res}.", "success")
    else:
        flash(res, "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/system-health")
def system_health():
    health_data = get_system_health()
    return render_template("admin/system_health.html", health=health_data)


@admin_bp.route("/audit-logs")
def audit_logs():
    entity_filter = request.args.get("entity")
    logs = get_audit_logs(limit=100, entity_name=entity_filter if entity_filter else None)
    settings = get_system_settings_list()
    return render_template(
        "admin/audit_logs.html",
        logs=logs,
        settings=settings,
        selected_entity=entity_filter
    )


@admin_bp.route("/settings/update", methods=["POST"])
def update_setting_route():
    key = request.form.get("setting_key")
    val = request.form.get("setting_value")
    success, msg = update_system_setting(key, val, user_id=get_current_user_id())
    flash(msg, "success" if success else "danger")
    return redirect(url_for("admin.audit_logs"))


@admin_bp.route("/enquiries")
def enquiries():
    status_filter = request.args.get("status", "").strip().upper()
    if status_filter not in VALID_ENQUIRY_STATUSES:
        status_filter = ""
    messages = get_contact_messages(status=status_filter or None, limit=150)
    return render_template(
        "admin/enquiries.html",
        messages=messages,
        selected_status=status_filter,
        valid_statuses=VALID_ENQUIRY_STATUSES,
    )


@admin_bp.route("/enquiries/<int:message_id>/status", methods=["POST"])
def update_enquiry_status(message_id):
    new_status = request.form.get("submission_status", "")
    admin_id = get_current_user_id()
    success, res = update_contact_status(message_id, new_status)
    if success:
        log_audit_event(
            action="UPDATE_ENQUIRY_STATUS",
            entity_name="ContactMessages",
            entity_id=message_id,
            user_id=admin_id,
            details=f"Admin updated enquiry #{message_id} status to {res}",
            ip_address=request.remote_addr,
        )
        flash(f"Enquiry #{message_id} marked as {res}.", "success")
    else:
        flash(res, "danger")
    return redirect(url_for("admin.enquiries"))


@admin_bp.route("/data-sources")
def admin_data_sources():
    """Admin Data Source Register & Integrity Governance portal."""
    return render_template(
        "admin/data_sources.html",
        sources=get_data_sources(),
        valid_statuses=VALID_DATA_STATUSES,
    )


@admin_bp.route("/data-sources/<int:source_id>/update", methods=["POST"])
def update_data_source_route(source_id):
    new_status = request.form.get("data_status", "")
    notes = request.form.get("notes", "")
    success, msg = update_data_source(source_id, new_status, notes=notes or None)
    if success:
        log_audit_event(
            action="UPDATE_DATA_SOURCE",
            entity_name="DataSources",
            entity_id=source_id,
            user_id=get_current_user_id(),
            details=msg,
            ip_address=request.remote_addr,
        )
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.admin_data_sources"))


@admin_bp.route("/users/<int:user_id>")
def user_detail(user_id):
    """Detailed inspection of an individual customer, owner or admin profile."""
    from app.services.auth_service import get_user_profile
    target_user = get_user_profile(user_id)
    if not target_user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))

    from app.services.vehicle_service import get_vehicles_by_user
    vehicles = get_vehicles_by_user(user_id)

    owned_stations = query_all(
        "SELECT s.*, COUNT(cp.point_id) AS total_points "
        "FROM Stations s "
        "LEFT JOIN ChargingPoints cp ON cp.station_id = s.station_id "
        "WHERE s.owner_user_id = %s "
        "GROUP BY s.station_id",
        (user_id,)
    )

    bookings = query_all(
        "SELECT b.*, cp.point_code, cp.connector_type, s.station_name, v.registration_no "
        "FROM Bookings b "
        "LEFT JOIN ChargingPoints cp ON cp.point_id = b.point_id "
        "LEFT JOIN Stations s ON s.station_id = cp.station_id "
        "LEFT JOIN Vehicles v ON v.vehicle_id = b.vehicle_id "
        "WHERE b.user_id = %s ORDER BY b.start_at DESC LIMIT 10",
        (user_id,)
    )

    sessions = query_all(
        "SELECT cs.*, cp.point_code, s.station_name, v.registration_no "
        "FROM ChargingSessions cs "
        "LEFT JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "LEFT JOIN Stations s ON s.station_id = cp.station_id "
        "LEFT JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "WHERE cs.user_id = %s ORDER BY cs.start_at DESC LIMIT 10",
        (user_id,)
    )

    return render_template(
        "admin/user_detail.html",
        user=target_user,
        vehicles=vehicles,
        owned_stations=owned_stations,
        bookings=bookings,
        sessions=sessions,
    )


@admin_bp.route("/owner-applications")
def owner_applications():
    search_q = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "").strip().upper() or None
    from app.services.owner_service import get_owner_applications
    applications = get_owner_applications(status=status_filter, search=search_q)
    stations_list = get_all_stations()
    return render_template(
        "admin/owner_applications.html",
        applications=applications,
        stations=stations_list,
        search_query=search_q,
        selected_status=status_filter or "",
    )


@admin_bp.route("/owner-applications/<int:application_id>/review", methods=["POST"])
def review_owner_application_route(application_id):
    admin_id = get_current_user_id()
    action = request.form.get("action", "").strip().upper()
    admin_notes = request.form.get("admin_notes", "").strip()
    assign_station_id = request.form.get("assign_station_id", type=int)

    from app.services.owner_service import review_owner_application
    success, err = review_owner_application(
        application_id=application_id,
        admin_user_id=admin_id,
        action=action,
        admin_notes=admin_notes,
        assign_station_id=assign_station_id,
    )
    if not success:
        flash(err, "danger")
    else:
        flash(f"Application #{application_id} has been {action.lower()}.", "success")
    return redirect(url_for("admin.owner_applications"))


