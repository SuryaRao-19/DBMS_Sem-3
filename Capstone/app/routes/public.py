"""
Public Portal Routes, Brand Reference, Map Discovery & Web3Forms Contact
EV Charging Station Management System
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, abort
from app.routes.auth_middleware import login_required, role_required, get_current_user_id
from app.services.station_service import get_all_stations, get_station_by_id, get_station_by_slug, get_all_charging_points
from app.services.qr_service import (
    record_qr_scan_by_token,
    get_or_create_station_qr,
    render_qr_png_bytes,
    record_point_qr_scan_by_token,
    get_booking_qr_by_token,
    mark_booking_qr_verified,
)
from app.services.report_service import get_admin_dashboard_metrics
from app.services.auth_service import get_user_profile, update_user_profile
from app.services.contact_service import CONTACT_CATEGORIES, submit_contact_enquiry
from app.services.platform_service import VERIFIED_ANNOUNCEMENTS, OFFICIAL_EZCHARGE_STATS, get_data_sources
from app.services.api_health_service import get_station_provenance_meta, get_api_integration_overview

public_bp = Blueprint("public", __name__)

NCR_CITIES = ("New Delhi", "Gurugram", "Noida", "Greater Noida", "Faridabad", "Ghaziabad")


def _matches_speed_bucket(dispensers, speed_filter):
    if not speed_filter:
        return True
    speeds = [float(p.get("max_power_kw") or 0) for p in dispensers]
    if not speeds:
        return False
    peak = max(speeds)
    if speed_filter == "FAST":
        return peak >= 50.0
    if speed_filter == "RAPID":
        return 22.0 <= peak < 50.0
    if speed_filter == "AC":
        return any(s < 22.0 for s in speeds)
    return True


@public_bp.route("/api/index")
def vercel_entrypoint_redirect():
    """Fallback handler when Vercel serverless functions invoke /api/index directly."""
    return landing()


@public_bp.route("/")
def landing():
    """Public landing page with verified reference identity, NCR stations, and map preview."""
    try:
        metrics = get_admin_dashboard_metrics()
    except Exception:
        metrics = {
            "total_users": 0, "total_stations": 0, "total_chargers": 0,
            "total_sessions": 0, "total_revenue": 0, "total_energy_kwh": 0,
            "verified_stations": 0,
        }
    try:
        stations = get_all_stations(status="ACTIVE", only_approved=True)
    except Exception:
        stations = []
    cities = sorted(list(set(s["city"] for s in stations if s.get("city"))))

    return render_template(
        "landing.html",
        metrics=metrics,
        featured_stations=stations[:6],
        all_stations=stations,
        cities=cities,
        ncr_cities=NCR_CITIES,
        announcements=VERIFIED_ANNOUNCEMENTS,
        official_stats=OFFICIAL_EZCHARGE_STATS,
        contact_categories=CONTACT_CATEGORIES,
        city_count=len(cities),
        station_count=len(stations),
    )


@public_bp.route("/about")
def about():
    """About Us page detailing verified Tata Power EZ Charge case study & data transparency."""
    data_sources = get_data_sources()
    try:
        stations = get_all_stations(status="ACTIVE", only_approved=True)
    except Exception:
        stations = []
    city_counts = {}
    for s in stations:
        city_counts[s["city"]] = city_counts.get(s["city"], 0) + 1

    return render_template(
        "about.html",
        data_sources=data_sources,
        announcements=VERIFIED_ANNOUNCEMENTS,
        official_stats=OFFICIAL_EZCHARGE_STATS,
        city_counts=city_counts,
        total_verified=sum(1 for s in stations if s.get("verification_status") == "VERIFIED"),
    )


@public_bp.route("/data-sources")
def data_sources():
    """Public Data Source Register documenting A/B/C/D provenance categories & free API licenses."""
    return render_template(
        "data_sources.html",
        sources=get_data_sources(),
        api_overview=get_api_integration_overview(),
    )


@public_bp.route("/stations")
def browse_stations():
    """Public interactive map and charging station directory with NCR city, connector, and speed filters."""
    city_filter = request.args.get("city", "").strip()
    connector_filter = request.args.get("connector", "").strip()
    speed_filter = request.args.get("speed", "").strip().upper()
    query = request.args.get("q", "").strip().lower()

    try:
        all_active_stations = get_all_stations(status="ACTIVE", only_approved=True)
    except Exception:
        all_active_stations = []
    available_cities = sorted(list(set(s["city"] for s in all_active_stations if s.get("city"))))

    stations_for_city = (
        [s for s in all_active_stations if s["city"].lower() == city_filter.lower()]
        if city_filter
        else all_active_stations
    )
    try:
        all_points = get_all_charging_points(only_approved=True)
    except Exception:
        all_points = []
    available_connectors = sorted(list(set(p["connector_type"] for p in all_points if p.get("connector_type"))))

    points_by_station = {}
    for p in all_points:
        points_by_station.setdefault(p["station_id"], []).append(p)

    filtered_stations = []
    for s in stations_for_city:
        st_points = points_by_station.get(s["station_id"], [])

        if connector_filter:
            has_conn = any(p["connector_type"] == connector_filter for p in st_points) or (
                connector_filter.lower() in (s.get("connector_types") or "").lower()
            )
            if not has_conn:
                continue

        if speed_filter and not _matches_speed_bucket(st_points, speed_filter):
            continue

        if query:
            searchable = " ".join([
                s.get("station_name") or "",
                s.get("city") or "",
                s.get("state") or "",
                s.get("postal_code") or "",
                s.get("address") or "",
                s.get("operator_name") or "",
            ]).lower()
            if query not in searchable:
                continue

        s["dispensers"] = st_points
        filtered_stations.append(s)

    return render_template(
        "public_stations.html",
        stations=filtered_stations,
        cities=available_cities,
        ncr_cities=NCR_CITIES,
        connectors=available_connectors,
        selected_city=city_filter,
        selected_connector=connector_filter,
        selected_speed=speed_filter,
        search_query=query,
    )


@public_bp.route("/stations/<int:station_id>")
def station_detail(station_id):
    """Detailed view of a charging station with geospatial coordinates, facilities, and dispensers."""
    station = get_station_by_id(station_id, only_approved=True)
    if not station:
        flash("Charging station not found.", "danger")
        return redirect(url_for("public.browse_stations"))

    prov = get_station_provenance_meta(station["station_id"])
    if prov:
        station.update(prov)
    station_qr = get_or_create_station_qr(station["station_id"])
    return render_template("station_detail.html", station=station, station_qr=station_qr, qr_verified=False)


@public_bp.route("/station/<slug>")
def station_by_slug(slug):
    """Canonical opaque/slugged Station Identification page opened directly or via Station QR scan."""
    station = get_station_by_slug(slug, only_approved=True)
    if not station:
        flash("Charging station not found.", "danger")
        return redirect(url_for("public.browse_stations"))

    prov = get_station_provenance_meta(station["station_id"])
    if prov:
        station.update(prov)
    station_qr = get_or_create_station_qr(station["station_id"])
    return render_template(
        "station_detail.html",
        station=station,
        station_qr=station_qr,
        qr_verified=(request.args.get("qr") == "verified"),
    )


@public_bp.route("/qr/station/<token>")
def scan_station_qr(token):
    """
    Public endpoint encoded inside physical Station Identification QR stickers.
    Validates opaque token (rejecting revoked, expired, or invalid tokens) and opens the station view.
    """
    qr_row, err_msg, status_code = record_qr_scan_by_token(token)
    if err_msg:
        return render_template("qr_status.html", error_message=err_msg, status_code=status_code), status_code

    slug = qr_row.get("station_slug")
    if slug:
        return redirect(url_for("public.station_by_slug", slug=slug, qr="verified"))
    return redirect(url_for("public.station_detail", station_id=qr_row["station_id"]))


@public_bp.route("/qr/station/<token>/image.png")
def station_qr_image(token):
    """Serve local PNG image for an active Station Identification QR without incrementing scan telemetry."""
    base = request.url_root.rstrip("/")
    scan_url = f"{base}{url_for('public.scan_station_qr', token=token)}"
    return Response(render_qr_png_bytes(scan_url), mimetype="image/png")


@public_bp.route("/qr/point/<token>")
def scan_point_qr(token):
    """Public/driver endpoint encoded inside Charging Point Identification QRs."""
    row, err_msg, status_code = record_point_qr_scan_by_token(token)
    if err_msg:
        return render_template("qr_status.html", error_message=err_msg, status_code=status_code), status_code
    return render_template("qr_point.html", point=row)


@public_bp.route("/qr/point/<token>/image.png")
def point_qr_image(token):
    """Serve local PNG image for an active Charging Point Identification QR."""
    base = request.url_root.rstrip("/")
    scan_url = f"{base}{url_for('public.scan_point_qr', token=token)}"
    return Response(render_qr_png_bytes(scan_url), mimetype="image/png")


@public_bp.route("/qr/booking/<token>")
@login_required
def scan_booking_qr(token):
    """Strict RBAC-scoped Booking Check-In Verification view (customer, owner partner, or ADMIN)."""
    row = get_booking_qr_by_token(token)
    if not row:
        return render_template("qr_status.html", error_message="Invalid Booking QR token.", status_code=404), 404
    uid = get_current_user_id()
    user_role = session.get("role")
    is_admin = (user_role == "ADMIN")
    is_customer_owner = (row["user_id"] == uid)
    is_station_partner = (user_role == "OWNER" and row.get("owner_user_id") == uid)
    if not (is_admin or is_customer_owner or is_station_partner):
        abort(403)
    return render_template("qr_booking.html", booking_qr=row, can_checkin=(is_admin or is_station_partner))


@public_bp.route("/qr/booking/<token>/checkin", methods=["POST"])
@login_required
def checkin_booking_qr(token):
    """Admin or Station Partner check-in confirmation for a Booking QR."""
    booking_meta = get_booking_qr_by_token(token)
    if not booking_meta:
        return render_template("qr_status.html", error_message="Invalid Booking QR token.", status_code=404), 404

    uid = get_current_user_id()
    user_role = session.get("role")
    is_admin = (user_role == "ADMIN")
    is_station_partner = (user_role == "OWNER" and booking_meta.get("owner_user_id") == uid)
    if not (is_admin or is_station_partner):
        abort(403)

    row, err_msg, status_code = mark_booking_qr_verified(token)
    if err_msg:
        flash(err_msg, "danger")
        return redirect(url_for("admin.bookings") if is_admin else url_for("owner.bookings"))
    flash(f"Booking #{row['booking_id']} check-in QR verified successfully.", "success")
    return redirect(url_for("public.scan_booking_qr", token=token))


@public_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile view and credential management for both EV Owners and Administrators."""
    user_id = get_current_user_id()
    user_data = get_user_profile(user_id)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_new_password = request.form.get("confirm_new_password", "").strip()

        if not full_name:
            flash("Full name cannot be empty.", "danger")
            return render_template("profile.html", user=user_data)

        if new_password:
            if new_password != confirm_new_password:
                flash("New passwords do not match.", "danger")
                return render_template("profile.html", user=user_data)
            if len(new_password) < 6:
                flash("New password must be at least 6 characters.", "danger")
                return render_template("profile.html", user=user_data)

        success, err = update_user_profile(
            user_id,
            full_name=full_name,
            phone=phone,
            current_password=current_password if new_password else None,
            new_password=new_password if new_password else None,
        )

        if success:
            session["full_name"] = full_name
            flash("Profile updated successfully!", "success")
            user_data = get_user_profile(user_id)
        else:
            flash(err, "danger")

    return render_template("profile.html", user=user_data)


@public_bp.route("/contact", methods=["GET", "POST"])
def contact():
    """Public Contact Us & Support Enquiry portal (Web3Forms proxy + MySQL backup + official social references)."""
    form_data = {}
    uid = get_current_user_id()
    if request.method == "GET" and uid:
        profile_data = get_user_profile(uid)
        if profile_data:
            form_data = {
                "full_name": profile_data.get("full_name", ""),
                "email": profile_data.get("email", ""),
                "phone": profile_data.get("phone") or "",
            }

    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        subject = request.form.get("subject", "")
        category = request.form.get("category", "")
        message = request.form.get("message", "")
        honeypot = request.form.get("botcheck", "")

        form_data = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "subject": subject,
            "category": category,
            "message": message,
        }

        ip_addr = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
        contact_id, delivered, feedback_msg, is_val_err = submit_contact_enquiry(
            full_name=full_name,
            email=email,
            phone=phone,
            subject=subject,
            category=category,
            message=message,
            honeypot=honeypot,
            ip_address=ip_addr,
        )

        if is_val_err:
            flash(feedback_msg, "danger")
            return render_template(
                "contact.html",
                categories=CONTACT_CATEGORIES,
                form_data=form_data,
            ), 400

        if not delivered:
            flash(feedback_msg, "danger")
            return render_template(
                "contact.html",
                categories=CONTACT_CATEGORIES,
                form_data=form_data,
                saved_contact_id=contact_id,
            ), 502

        flash(feedback_msg, "success")
        return redirect(url_for("public.contact"))

    return render_template(
        "contact.html",
        categories=CONTACT_CATEGORIES,
        form_data=form_data,
    )


@public_bp.route("/privacy")
def privacy():
    """Academic platform privacy and test-mode data policy."""
    return render_template("privacy.html")


@public_bp.route("/terms")
def terms():
    """Academic platform terms, trademark disclaimer & Razorpay test-mode policy."""
    return render_template("terms.html")
