"""
Phase 10 Verification Tests: Real-World Brand Identity, NCR Geospatial Stations,
CSV Import & Approval Workflow, Data Integrity Register, and Demo Payment Simulation.
"""
from app.db import execute, query_one
from app.services.station_import_service import import_stations_from_csv


def test_real_world_identity_about_data_sources_and_social_links(client):
    """Verify official Tata Power EZ Charge reference branding, disclaimer, and social links."""
    res_home = client.get("/")
    assert res_home.status_code == 200
    home_html = res_home.data.decode("utf-8")
    assert "EV ChargeNet" in home_html
    assert "Tata Power EZ Charge" in home_html
    assert "700+" in home_html
    assert "landingMap" in home_html
    assert "support@evchargenet.com" not in home_html

    # Footer / layout external social links must open in new tab safely
    expected_socials = [
        "https://www.linkedin.com/company/tata-power/",
        "https://x.com/tatapower",
        "https://www.instagram.com/tatapowercompanyltd/",
        "https://www.facebook.com/tatapower/",
    ]
    for url in expected_socials:
        assert f'href="{url}" target="_blank" rel="noopener noreferrer"' in home_html

    # YouTube official channel URL requested by prompt
    assert (
        'href="https://www.youtube.com/channel/UCCz5pvnMkswgbWh5MKMH-vQ" target="_blank" rel="noopener noreferrer"' in home_html
        or 'href="https://www.youtube.com/@TataPowerCompanyLtd" target="_blank" rel="noopener noreferrer"' in home_html
    )

    # Official website, EZ Charge, and Linktree presence
    assert 'href="https://www.tatapower.com/" target="_blank" rel="noopener noreferrer"' in home_html
    assert 'href="https://www.tatapower.com/ezcharge" target="_blank" rel="noopener noreferrer"' in home_html
    assert 'href="https://linktr.ee/Tata_Power_EZ_Charge" target="_blank" rel="noopener noreferrer"' in home_html

    res_about = client.get("/about")
    assert res_about.status_code == 200
    about_html = res_about.data.decode("utf-8")
    assert "independent academic" in about_html.lower()
    assert "Empower a billion lives through sustainable" in about_html
    assert "1800 833 2233" in about_html
    assert "evsupport@tatapower.com" in about_html

    res_sources = client.get("/data-sources")
    assert res_sources.status_code == 200
    sources_html = res_sources.data.decode("utf-8")
    assert "Data Source Register" in sources_html
    assert "tatapower.com/ezcharge" in sources_html
    assert "VERIFIED" in sources_html
    assert "DEMO" in sources_html


def test_ncr_stations_geospatial_api_and_filters(client):
    """Verify all 6 Delhi NCR regions exist with valid real-world coordinates and filtering."""
    res = client.get("/api/stations/map")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["success"] is True
    assert payload["count"] >= 14

    cities = {s["city"] for s in payload["stations"]}
    for expected_city in ("New Delhi", "Gurugram", "Noida", "Greater Noida", "Faridabad", "Ghaziabad"):
        assert expected_city in cities

    for st in payload["stations"]:
        lat = float(st["latitude"])
        lng = float(st["longitude"])
        # Realistic Delhi NCR bounding box
        assert 28.0 <= lat <= 29.0
        assert 76.8 <= lng <= 77.8
        assert st["postal_code"] and len(str(st["postal_code"])) == 6
        assert st["maps_url"].startswith("https://")
        assert st["operator_name"]

    # City & speed filter
    res_ggn = client.get("/api/stations/map?city=Gurugram&speed=FAST")
    assert res_ggn.status_code == 200
    ggn_data = res_ggn.get_json()
    assert ggn_data["count"] >= 1
    assert all(s["city"] == "Gurugram" for s in ggn_data["stations"])


def test_csv_import_validation_pending_gate_and_admin_approval(admin_client, owner_client):
    """
    Verify CSV station import validates coordinates/PIN/source_url, skips duplicates,
    isolates non-admins, holds imported hubs as PENDING_APPROVAL until approved, then publishes.
    """
    # Owner cannot access CSV import or station review
    res_owner_imp = owner_client.post("/admin/stations/import", data={"csv_text": ""})
    assert res_owner_imp.status_code == 403

    # Validation rejections & duplicate skip in service
    bad_csv = (
        "station_name,address,city,state,postal_code,latitude,longitude,operator_name,"
        "connector_types,charger_capacity_kw,source_url,facilities\n"
        # Bad coordinates outside India
        "Invalid Coords Hub,Somewhere Rd,Noida,Uttar Pradesh,201301,51.5074,-0.1278,Tata Power EZ Charge,"
        "CCS2,60 kW,https://www.tatapower.com/ezcharge/,Parking\n"
        # Invalid PIN code
        "Invalid Pin Hub,Somewhere Rd,Noida,Uttar Pradesh,12AB,28.5700,77.3200,Tata Power EZ Charge,"
        "CCS2,60 kW,https://www.tatapower.com/ezcharge/,Parking\n"
        # Missing source URL
        "No Source Hub,Somewhere Rd,Noida,Uttar Pradesh,201301,28.5700,77.3200,Tata Power EZ Charge,"
        "CCS2,60 kW,,Parking\n"
        # Duplicate existing station coordinates/name
        "Connaught Place EV Hub,Bangla Sahib Rd Connaught Place,New Delhi,Delhi,110001,28.6280,77.2090,"
        "Tata Power EZ Charge,CCS2,60 kW,https://www.tatapower.com/ezcharge/,Parking\n"
    )
    bad_res = import_stations_from_csv(bad_csv)
    assert len(bad_res["imported_ids"]) == 0
    assert len(bad_res["errors"]) == 3
    assert len(bad_res["skipped"]) == 1

    unique_name = "Test Dwarka Sector 21 EZ Hub"
    execute("DELETE FROM Stations WHERE station_name = %s", (unique_name,))
    good_csv = (
        "station_name,address,city,state,postal_code,latitude,longitude,operator_name,"
        "connector_types,charger_capacity_kw,source_url,facilities\n"
        f"{unique_name},Dwarka Sector 21 Metro Complex,New Delhi,Delhi,110077,28.5522,77.0583,"
        "Tata Power EZ Charge,CCS2; Type 2 AC,60 kW DC Fast,https://www.tatapower.com/ezcharge/,Parking;Restroom\n"
    )

    created_id = None
    try:
        res_imp = admin_client.post(
            "/admin/stations/import",
            data={"csv_text": good_csv},
            follow_redirects=True,
        )
        assert res_imp.status_code == 200
        assert "queued for admin approval" in res_imp.data.decode("utf-8")

        row = query_one(
            "SELECT station_id, approval_status, verification_status, postal_code "
            "FROM Stations WHERE station_name = %s",
            (unique_name,),
        )
        assert row is not None
        created_id = row["station_id"]
        assert row["approval_status"] == "PENDING_APPROVAL"
        assert row["postal_code"] == "110077"

        # Hidden from public map until approved
        map_before = admin_client.get("/api/stations/map").get_json()
        assert all(s["station_id"] != created_id for s in map_before["stations"])

        # Non-admin blocked from approving
        res_owner_rev = owner_client.post(
            f"/admin/stations/{created_id}/review",
            data={"decision": "APPROVED"},
        )
        assert res_owner_rev.status_code == 403

        # Admin approves with VERIFIED status
        res_approve = admin_client.post(
            f"/admin/stations/{created_id}/review",
            data={"decision": "APPROVED", "verification_status": "VERIFIED"},
            follow_redirects=True,
        )
        assert res_approve.status_code == 200

        row_after = query_one(
            "SELECT approval_status, verification_status FROM Stations WHERE station_id = %s",
            (created_id,),
        )
        assert row_after["approval_status"] == "APPROVED"
        assert row_after["verification_status"] == "VERIFIED"

        # Now visible on public geospatial feed
        map_after = admin_client.get("/api/stations/map").get_json()
        assert any(s["station_id"] == created_id for s in map_after["stations"])
    finally:
        if created_id:
            execute("DELETE FROM StationFacilities WHERE station_id = %s", (created_id,))
            execute("DELETE FROM ChargingPoints WHERE station_id = %s", (created_id,))
            execute("DELETE FROM Stations WHERE station_id = %s", (created_id,))


def test_demo_payment_simulation_retry_receipt_download_and_idor(owner_client, other_owner_client):
    """
    Verify simulated payment methods (CREDIT_CARD, DEBIT_CARD, NET_BANKING), FAILED -> retry SUCCESS,
    duplicate SUCCESS protection, downloadable .txt receipt, and cross-user IDOR blocking.
    """
    session_id = None
    session_cc_id = None
    try:
        # Insert clean completed sessions belonging to owner_client (user_id=2, vehicle_id=1, point_id=2)
        session_id = execute(
            "INSERT INTO ChargingSessions "
            "(user_id, vehicle_id, point_id, start_at, end_at, energy_kwh, tariff_per_kwh, total_cost, session_status) "
            "VALUES (%s, %s, %s, DATE_SUB(NOW(), INTERVAL 30 MINUTE), NOW(), 12.50, 18.00, 225.00, 'COMPLETED')",
            (2, 1, 2),
        )
        session_cc_id = execute(
            "INSERT INTO ChargingSessions "
            "(user_id, vehicle_id, point_id, start_at, end_at, energy_kwh, tariff_per_kwh, total_cost, session_status) "
            "VALUES (%s, %s, %s, DATE_SUB(NOW(), INTERVAL 45 MINUTE), DATE_SUB(NOW(), INTERVAL 15 MINUTE), 10.00, 18.00, 180.00, 'COMPLETED')",
            (2, 1, 2),
        )

        # HTML form simulated CREDIT_CARD payment
        res_cc = owner_client.post(
            "/owner/charging",
            data={"action": "pay", "session_id": str(session_cc_id), "payment_method": "CREDIT_CARD", "simulated_outcome": "SUCCESS"},
            follow_redirects=True,
        )
        assert res_cc.status_code == 200
        assert "DEMO PAYMENT SUCCESSFUL" in res_cc.data.decode("utf-8")

        # 1. Simulate FAILED Debit Card payment
        res_fail = owner_client.post(
            "/api/session/pay",
            json={
                "session_id": session_id,
                "payment_method": "DEBIT_CARD",
                "simulated_outcome": "FAILED",
            },
        )
        assert res_fail.status_code == 200
        fail_json = res_fail.get_json()
        assert fail_json["success"] is True
        assert fail_json["status"] == "FAILED"

        # 2. Retry same session with NET_BANKING -> SUCCESS
        res_retry = owner_client.post(
            "/api/session/pay",
            json={
                "session_id": session_id,
                "payment_method": "NET_BANKING",
                "simulated_outcome": "SUCCESS",
            },
        )
        assert res_retry.status_code == 200
        ok_json = res_retry.get_json()
        assert ok_json["success"] is True
        assert ok_json["status"] == "SUCCESS"
        assert ok_json["amount"] == 225.0

        # 3. Duplicate payment after SUCCESS must fail with 400
        res_dup = owner_client.post(
            "/api/session/pay",
            json={
                "session_id": session_id,
                "payment_method": "CREDIT_CARD",
                "simulated_outcome": "SUCCESS",
            },
        )
        assert res_dup.status_code == 400

        # 4. Downloadable .txt demo receipt works for owner, blocked for other owner
        res_txt = owner_client.get(f"/owner/session/{session_id}/download")
        assert res_txt.status_code == 200
        assert "text/plain" in res_txt.content_type
        txt_body = res_txt.data.decode("utf-8")
        assert "DEMO PAYMENT RECEIPT" in txt_body
        assert "NO REAL MONEY CHARGED" in txt_body
        assert "NET_BANKING" in txt_body

        res_idor = other_owner_client.get(f"/owner/session/{session_id}/download")
        assert res_idor.status_code in (302, 403, 404)
        if res_idor.status_code == 302:
            assert "/owner/history" in res_idor.location
    finally:
        for sid in (session_id, session_cc_id):
            if sid:
                execute("DELETE FROM Payments WHERE session_id = %s", (sid,))
                execute("DELETE FROM ChargingSessions WHERE session_id = %s", (sid,))


def test_admin_dashboard_and_data_sources_governance(admin_client, owner_client, client):
    """Verify admin dashboard links, RBAC on /admin/data-sources, and status updates."""
    # Dashboard renders cleanly with new Data Sources / Enquiries links
    res_dash = admin_client.get("/admin/dashboard")
    assert res_dash.status_code == 200
    assert "Demo Ledger Revenue" in res_dash.data.decode("utf-8")

    # RBAC checks
    assert client.get("/admin/data-sources").status_code == 302
    assert owner_client.get("/admin/data-sources").status_code == 403
    assert owner_client.post("/admin/data-sources/1/update", data={"data_status": "DEMO"}).status_code == 403

    res_page = admin_client.get("/admin/data-sources")
    assert res_page.status_code == 200
    assert "Data Source Register" in res_page.data.decode("utf-8")

    orig = query_one("SELECT source_id, data_status, notes FROM DataSources ORDER BY source_id LIMIT 1")
    assert orig is not None
    try:
        res_upd = admin_client.post(
            f"/admin/data-sources/{orig['source_id']}/update",
            data={"data_status": "ESTIMATED", "notes": "Temporarily flagged for QA check"},
            follow_redirects=True,
        )
        assert res_upd.status_code == 200
        updated = query_one("SELECT data_status, notes FROM DataSources WHERE source_id = %s", (orig["source_id"],))
        assert updated["data_status"] == "ESTIMATED"
        assert "Temporarily flagged" in (updated["notes"] or "")
    finally:
        execute(
            "UPDATE DataSources SET data_status = %s, notes = %s WHERE source_id = %s",
            (orig["data_status"], orig["notes"], orig["source_id"]),
        )


def test_env_contract_dialect_isolation_and_demo_disclaimers(client):
    """
    Verify .env.example entries, Git exclusion of .env, rejection of non-MySQL PostgreSQL URLs,
    absence of credential leakage in public endpoints, and explicit demo tariff/bay labels.
    """
    from pathlib import Path
    import pytest
    from app.db import parse_database_url

    root = Path(__file__).resolve().parent.parent
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    for key in ("SUPABASE_URL=", "SUPABASE_PUBLISHABLE_KEY=", "WEB3FORMS_ACCESS_KEY="):
        assert key in env_example

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()

    # Never mix MySQL queries against a PostgreSQL/Supabase URL
    with pytest.raises(ValueError):
        parse_database_url("postgresql://postgres:secret@db.example.supabase.co:5432/postgres")

    # Station detail explicitly flags demo tariff rate and demo bay state
    st_res = client.get("/stations/1")
    assert st_res.status_code == 200
    st_html = st_res.data.decode("utf-8")
    assert "Demo Tariff Rate" in st_html
    assert "DEMO BAY STATE" in st_html
    assert "SUPABASE_SERVICE_ROLE_KEY" not in st_html

    # Health check never exposes passwords or access keys
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    health_text = health_res.data.decode("utf-8")
    assert "MYSQL_PASSWORD" not in health_text
    assert "WEB3FORMS_ACCESS_KEY" not in health_text
    assert "SUPABASE_" not in health_text
