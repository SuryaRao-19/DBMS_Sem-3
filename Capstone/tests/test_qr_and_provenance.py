"""
Verification Suite: Dual QR Workflows, Data Provenance, Null-Coordinate Map Gate,
Dynamic Payment QR Expiry, 7 Admin Charts, Legal Pages, and Oct 2026 Reference Data.
"""
import uuid
from app.db import execute, query_one
from tests.test_razorpay_checkout import _create_completed_test_session, _cleanup_test_session


def test_station_identification_qr_lifecycle_and_telemetry(client, admin_client, owner_client):
    """
    Verify Station Identification QR generation, PNG/SVG/Print endpoints,
    opaque token scan counting -> /station/<slug> redirect, revocation (410),
    regeneration invalidating old tokens, and non-admin access guard.
    """
    station_id = execute(
        "INSERT INTO Stations "
        "(station_name, station_slug, address, city, state, postal_code, latitude, longitude, "
        " operator_name, station_status, verification_status, approval_status, record_origin, is_demo) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 'VERIFIED', 'APPROVED', 'VERIFIED_PUBLIC_SOURCE', 0)",
        (
            "Test Janpath QR Hub",
            f"test-janpath-qr-{uuid.uuid4().hex[:6]}",
            "15 Janpath Rd",
            "New Delhi",
            "Delhi",
            "110001",
            28.6200,
            77.2100,
            "Tata Power EZ Charge",
        ),
    )

    try:
        # 1. Non-admin cannot regenerate/revoke/print station QR
        assert owner_client.post(f"/admin/stations/{station_id}/qr/regenerate").status_code == 403
        assert owner_client.post(f"/admin/stations/{station_id}/qr/revoke").status_code == 403
        assert owner_client.get(f"/admin/stations/{station_id}/qr/png").status_code == 403

        # 2. Admin can download PNG, SVG, and printable placard
        png_res = admin_client.get(f"/admin/stations/{station_id}/qr/png")
        assert png_res.status_code == 200
        assert png_res.mimetype == "image/png"
        assert png_res.data.startswith(b"\x89PNG")

        svg_res = admin_client.get(f"/admin/stations/{station_id}/qr/svg")
        assert svg_res.status_code == 200
        assert "svg" in svg_res.data.decode("utf-8").lower()

        print_res = admin_client.get(f"/admin/stations/{station_id}/qr/print")
        assert print_res.status_code == 200
        assert "Test Janpath QR Hub" in print_res.data.decode("utf-8")

        qr_row = query_one(
            "SELECT qr_token, qr_status, scan_count FROM StationQRCodes "
            "WHERE station_id = %s ORDER BY qr_id DESC LIMIT 1",
            (station_id,),
        )
        assert qr_row is not None
        assert qr_row["qr_status"] == "ACTIVE"
        assert int(qr_row["scan_count"]) == 0
        first_token = qr_row["qr_token"]

        # 3. Preview image route serves PNG without incrementing scan telemetry
        img_res = client.get(f"/qr/station/{first_token}/image.png")
        assert img_res.status_code == 200
        assert img_res.data.startswith(b"\x89PNG")
        unchanged = query_one("SELECT scan_count FROM StationQRCodes WHERE qr_token = %s", (first_token,))
        assert int(unchanged["scan_count"]) == 0

        # 4. Scanning /qr/station/<token> increments scan_count and redirects to /station/<slug>
        scan_res = client.get(f"/qr/station/{first_token}", follow_redirects=False)
        assert scan_res.status_code in (301, 302)
        assert "/station/" in scan_res.headers["Location"]

        scan_follow = client.get(scan_res.headers["Location"])
        assert scan_follow.status_code == 200
        follow_html = scan_follow.data.decode("utf-8")
        assert "Station Identification QR Verified" in follow_html
        assert "Test Janpath QR Hub" in follow_html

        scanned_row = query_one(
            "SELECT scan_count, last_scanned_at FROM StationQRCodes WHERE qr_token = %s",
            (first_token,),
        )
        assert int(scanned_row["scan_count"]) == 1
        assert scanned_row["last_scanned_at"] is not None

        # 5. Regenerating token revokes previous token and issues fresh active token
        regen_res = admin_client.post(f"/admin/stations/{station_id}/qr/regenerate", follow_redirects=True)
        assert regen_res.status_code == 200

        old_scan = client.get(f"/qr/station/{first_token}")
        assert old_scan.status_code == 410
        assert "Station Identification QR Unavailable" in old_scan.data.decode("utf-8")

        new_qr = query_one(
            "SELECT qr_token, qr_status FROM StationQRCodes WHERE station_id = %s AND qr_status = 'ACTIVE'",
            (station_id,),
        )
        assert new_qr is not None and new_qr["qr_token"] != first_token

        # 6. Revoking active token blocks scans cleanly with HTTP 410
        rev_res = admin_client.post(f"/admin/stations/{station_id}/qr/revoke", follow_redirects=True)
        assert rev_res.status_code == 200
        revoked_scan = client.get(f"/qr/station/{new_qr['qr_token']}")
        assert revoked_scan.status_code == 410

        # 7. Unknown token returns 404
        assert client.get("/qr/station/nonexistent-token-xyz999").status_code == 404
    finally:
        execute("DELETE FROM StationQRCodes WHERE station_id = %s", (station_id,))
        execute("DELETE FROM Stations WHERE station_id = %s", (station_id,))


def test_null_coordinate_pending_verification_excluded_from_map_and_admin_verify(client, admin_client, owner_client):
    """
    Verify candidate press-release stations with NULL coordinates / PENDING_VERIFICATION
    appear in the directory with 'Location verification pending.' and never appear on /api/stations/map,
    while verified hubs (Dr. Ambedkar International Centre) plot cleanly.
    """
    # 1. Seeded candidate locations & verified 15 Janpath hub
    map_res = client.get("/api/stations/map")
    assert map_res.status_code == 200
    map_payload = map_res.get_json()
    map_names = [s["station_name"] for s in map_payload["stations"]]

    assert any("Ambedkar" in name for name in map_names)
    for st in map_payload["stations"]:
        assert st["latitude"] is not None and st["longitude"] is not None
        assert st["verification_status"] not in ("PENDING_VERIFICATION", "PENDING_REVIEW", "OUTDATED")

    # 2. Public directory explicitly displays "Location verification pending." for null-coord stations
    dir_res = client.get("/stations")
    assert dir_res.status_code == 200
    dir_html = dir_res.data.decode("utf-8")
    assert "Location verification pending." in dir_html
    assert "Availability not connected" in dir_html

    # 3. Admin can transition station verification_status and non-admin gets 403
    cand = query_one(
        "SELECT station_id FROM Stations WHERE verification_status = 'PENDING_VERIFICATION' LIMIT 1"
    )
    assert cand is not None
    cid = cand["station_id"]

    assert owner_client.post(f"/admin/stations/{cid}/verify", data={"verification_status": "HISTORICAL"}).status_code == 403
    res_hist = admin_client.post(
        f"/admin/stations/{cid}/verify",
        data={"verification_status": "HISTORICAL"},
        follow_redirects=True,
    )
    assert res_hist.status_code == 200
    updated = query_one("SELECT verification_status FROM Stations WHERE station_id = %s", (cid,))
    assert updated["verification_status"] == "HISTORICAL"

    # Restore original status
    admin_client.post(f"/admin/stations/{cid}/verify", data={"verification_status": "PENDING_VERIFICATION"})


def test_dynamic_payment_qr_generation_and_expiry_enforcement(owner_client, other_owner_client):
    """
    Verify POST /api/payments/razorpay/qr binds amount & expiry on server, blocks IDOR,
    never marks payment paid on generation, and enforces EXPIRED state when TTL lapses.
    """
    sid, _ = _create_completed_test_session(energy_kwh=15.0)
    try:
        # 1. Cross-user IDOR blocked with 403
        cross = other_owner_client.post("/api/payments/razorpay/qr", json={"session_id": sid})
        assert cross.status_code == 403

        # 2. Owner generates single-use Dynamic Payment QR (10-min TTL)
        res = owner_client.post("/api/payments/razorpay/qr", json={"session_id": sid})
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert data["mode"] == "TEST_MODE"
        qr = data["qr"]
        assert qr["payment_qr_id"].startswith(("qr_sim_", "qr_"))
        assert qr["qr_image_data_uri"].startswith("data:image/png;base64,")
        assert int(qr["ttl_seconds"]) == 600

        pay_row = query_one(
            "SELECT payment_status, payment_qr_id, qr_expires_at FROM Payments WHERE razorpay_order_id = %s",
            (qr["order_id"],),
        )
        assert pay_row["payment_status"] == "PENDING"
        assert pay_row["payment_qr_id"] == qr["payment_qr_id"]
        assert pay_row["qr_expires_at"] is not None

        # 3. Expire QR in database and confirm settlement attempt is blocked with EXPIRED status
        execute(
            "UPDATE Payments SET qr_expires_at = DATE_SUB(NOW(), INTERVAL 2 MINUTE) WHERE razorpay_order_id = %s",
            (qr["order_id"],),
        )
        expired_try = owner_client.post(
            "/api/payments/razorpay/sandbox-complete",
            json={"session_id": sid, "razorpay_order_id": qr["order_id"], "payment_method": "UPI"},
        )
        assert expired_try.status_code == 400
        assert "expired" in expired_try.get_json()["error"].lower()

        row_after = query_one("SELECT payment_status FROM Payments WHERE razorpay_order_id = %s", (qr["order_id"],))
        assert row_after["payment_status"] == "EXPIRED"
    finally:
        _cleanup_test_session(sid)


def test_admin_seven_charts_legal_routes_and_oct2026_homepage(client, admin_client):
    """Verify all 7+ Admin Chart.js canvases, legal routes (/privacy, /terms), and Oct 2026 homepage sections."""
    # Admin dashboard 7+ charts + separated provenance KPIs
    res_dash = admin_client.get("/admin/dashboard")
    assert res_dash.status_code == 200
    dash_html = res_dash.data.decode("utf-8")
    for cid in (
        "chartMonthlyBookings",
        "chartMonthlySessions",
        "chartCityStations",
        "chartCapacityDist",
        "chartBookingStatus",
        "chartPaymentStatus",
        "chartEnquiryStatus",
        "chartConnectorMix",
    ):
        assert cid in dash_html
    assert "TYPE A OFFICIAL REFERENCE" in dash_html

    # Legal routes
    assert client.get("/privacy").status_code == 200
    assert client.get("/terms").status_code == 200

    # Homepage Oct 2026 Press Release + Scope Conflict + Apps + Stay Connected
    home_html = client.get("/").data.decode("utf-8")
    for token in (
        "6,700+",
        "2.5 lakh+",
        "1,200+",
        "7 lakh+",
        "700+",
        "5,500+",
        "620+",
        "Home Charging",
        "Public Charging",
        "E-Bus Depot",
        "Stay Connected With Tata Power",
        "com.tatapower.evapp",
        "id1496350476",
    ):
        assert token.lower() in home_html.lower()

    assert (
        "https://www.youtube.com/channel/uccz5pvnmkswgbwh5mkmh-vq" in home_html.lower()
        or "https://www.youtube.com/@tatapowercompanyltd" in home_html.lower()
    )


def test_all_url_for_endpoints_privacy_sections_and_prod_debug_off(app, client, admin_client, owner_client, monkeypatch):
    """
    Verify zero unregistered url_for() references across templates/routes,
    complete Privacy Policy sections + public/dashboard route rendering, and
    strict DEBUG=False enforcement in production mode even if FLASK_DEBUG=1.
    """
    import re
    from pathlib import Path
    from app import create_app

    root = Path(__file__).resolve().parent.parent
    registered = {rule.endpoint for rule in app.url_map.iter_rules()}
    pattern = re.compile(r"url_for\(\s*['\"]([a-zA-Z0-9_.]+)['\"]")

    missing = []
    for folder in (root / "app" / "templates", root / "app" / "routes"):
        for path in sorted(folder.rglob("*")):
            if path.suffix not in (".html", ".py"):
                continue
            for m in pattern.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                if m.group(1) not in registered:
                    missing.append((str(path.relative_to(root)), m.group(1)))

    assert missing == [], f"Unregistered url_for() endpoints detected: {missing}"

    # Public + Auth routes all render 200 with zero BuildError
    for route in ("/", "/stations", "/about", "/data-sources", "/privacy", "/terms", "/contact", "/login", "/register"):
        assert client.get(route).status_code == 200

    # Privacy page contains all required policy sections and academic disclaimer
    priv_html = client.get("/privacy").data.decode("utf-8")
    for section in (
        "Information Collection",
        "Account Information",
        "Booking",
        "Payment Demonstration Information",
        "Contact Form Information",
        "Data Storage",
        "Data Security",
        "Third-Party Services",
        "User Rights",
        "Contact Information",
        "Independent Academic Demonstration",
    ):
        assert section in priv_html

    # Authenticated dashboards & sub-pages render 200 cleanly
    assert admin_client.get("/admin/dashboard").status_code == 200
    assert admin_client.get("/admin/enquiries").status_code == 200
    assert owner_client.get("/owner/dashboard").status_code == 200
    assert owner_client.get("/owner/history").status_code == 200
    assert owner_client.get("/profile").status_code == 200

    # Production config enforces DEBUG=False regardless of FLASK_DEBUG=1
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-key-min-32-chars")
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_USER", "root")
    monkeypatch.setenv("MYSQL_PASSWORD", "test")
    monkeypatch.setenv("MYSQL_DATABASE", "ev_charging_db")
    prod_app = create_app()
    assert prod_app.debug is False
    assert prod_app.config["DEBUG"] is False
