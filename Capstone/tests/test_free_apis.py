"""
Automated Tests for Free Public API Integrations, Caching, Provenance & Extended QR Architecture
Covers Phase A (http_client), Phase B (Open Charge Map + ChargeAlong), and subsequent phases.
"""
from unittest.mock import MagicMock, patch

from app.db import execute, query_one
from app.services.http_client import get_cached_payload, make_cache_key, request_json, set_cached_payload
from app.services.openchargemap_service import (
    CHARGEALONG_INVESTIGATION,
    parse_ocm_poi,
    sync_openchargemap_stations,
)
from app.services.geo_service import calculate_route, find_nearby_stations, geocode_address, reverse_geocode
from app.services.weather_service import get_station_weather
from app.services.pincode_service import lookup_indian_pincode


def test_http_client_mysql_cache_and_retry_recovery(app):
    """HTTP client should retry transient 503 responses with backoff and cache 200 JSON in MySQL ApiCache."""
    cache_key = make_cache_key("pytest_http", "retry_probe")
    execute("DELETE FROM ApiCache WHERE cache_key = %s", (cache_key,))

    resp_503 = MagicMock(status_code=503, text="Temporary Unavailable", reason="Service Unavailable")
    resp_200 = MagicMock(status_code=200)
    resp_200.json.return_value = {"status": "ok", "sample": 42}

    with app.app_context():
        with patch("app.services.http_client.requests.get", side_effect=[resp_503, resp_200]) as mock_get:
            res = request_json(
                provider="TestProvider",
                operation="retry_probe",
                url="https://example.invalid/test",
                max_retries=2,
                backoff_base_seconds=0.01,
                cache_key=cache_key,
                cache_ttl_seconds=300,
                log_success=False,
            )
            assert res["ok"] is True
            assert res["cached"] is False
            assert res["data"]["sample"] == 42
            assert mock_get.call_count == 2

        # Second call must be served directly from MySQL ApiCache without hitting requests.get
        with patch("app.services.http_client.requests.get") as mock_get_cached:
            res_cached = request_json(
                provider="TestProvider",
                operation="retry_probe",
                url="https://example.invalid/test",
                cache_key=cache_key,
                cache_ttl_seconds=300,
            )
            assert res_cached["ok"] is True
            assert res_cached["cached"] is True
            assert res_cached["data"]["sample"] == 42
            mock_get_cached.assert_not_called()

        cached_direct = get_cached_payload(cache_key)
        assert cached_direct == {"status": "ok", "sample": 42}

    execute("DELETE FROM ApiCache WHERE cache_key = %s", (cache_key,))


def test_chargealong_documented_as_non_india_unsupported():
    assert CHARGEALONG_INVESTIGATION["supported"] is False
    assert CHARGEALONG_INVESTIGATION["status"] == "EXCLUDED_UNSUPPORTED_REGION"
    assert "India" in CHARGEALONG_INVESTIGATION["reason"]


def test_ocm_poi_validation_and_bounds():
    valid_poi = {
        "ID": 999888,
        "AddressInfo": {
            "Title": "Connaught Place Community Charger",
            "AddressLine1": "Block A, Connaught Place",
            "Town": "New Delhi",
            "StateOrProvince": "Delhi",
            "Postcode": "110001",
            "Latitude": 28.6315,
            "Longitude": 77.2167,
        },
        "OperatorInfo": {"Title": "Statiq"},
        "Connections": [
            {"ConnectionType": {"Title": "CCS (Type 2)"}, "PowerKW": 60, "Quantity": 2},
            {"ConnectionType": {"Title": "Type 2 (Socket Only)"}, "PowerKW": 22, "Quantity": 1},
        ],
    }
    parsed = parse_ocm_poi(valid_poi)
    assert parsed is not None
    assert parsed["external_source_id"] == "OCM-999888"
    assert parsed["postal_code"] == "110001"
    assert parsed["gun_count"] == 3
    assert "CCS2" in parsed["connector_types"]
    assert "TYPE2" in parsed["connector_types"]
    assert parsed["points"][0]["point_status"] == "UNAVAILABLE"

    # Reject out-of-India coordinates cleanly
    foreign_poi = {
        "ID": 999889,
        "AddressInfo": {"Title": "London Hub", "Latitude": 51.5074, "Longitude": -0.1278},
    }
    assert parse_ocm_poi(foreign_poi) is None


def test_ocm_sync_skips_gracefully_without_key(app):
    with app.app_context():
        app.config["OPEN_CHARGE_MAP_API_KEY"] = ""
        res = sync_openchargemap_stations(api_key="")
        assert res["ok"] is False
        assert res["status"] == "SKIPPED_UNCONFIGURED"
        assert "OPEN_CHARGE_MAP_API_KEY" in res["message"]


def test_ocm_sync_persists_deduplicates_and_separates_provenance(app):
    mock_pois = [
        {
            "ID": 777001,
            "AddressInfo": {
                "Title": "OCM Synthetic Test Hub Saket",
                "AddressLine1": "Press Enclave Marg, Saket",
                "Town": "New Delhi",
                "StateOrProvince": "Delhi",
                "Postcode": "110017",
                "Latitude": 28.5285,
                "Longitude": 77.2190,
            },
            "OperatorInfo": {"Title": "Independent OCM Operator"},
            "Connections": [
                {"ConnectionType": {"Title": "CCS (Type 2)"}, "PowerKW": 50, "Quantity": 2}
            ],
        },
        # Exact duplicate external ID inside same payload batch
        {
            "ID": 777001,
            "AddressInfo": {
                "Title": "OCM Synthetic Test Hub Saket",
                "Latitude": 28.5285,
                "Longitude": 77.2190,
            },
        },
    ]

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = mock_pois

    execute("DELETE FROM Stations WHERE external_source_id = 'OCM-777001'")
    try:
        with app.app_context():
            with patch("app.services.http_client.requests.get", return_value=mock_resp):
                first = sync_openchargemap_stations(api_key="test-key-123")
                assert first["ok"] is True
                assert first["fetched"] == 2
                assert first["imported"] == 1
                assert first["duplicates"] == 1

                row = query_one(
                    "SELECT provenance_category, source_name, external_source_id, license_info FROM Stations WHERE external_source_id = 'OCM-777001'"
                )
                assert row is not None
                assert row["provenance_category"] == "B_THIRD_PARTY_API"
                assert row["source_name"] == "Open Charge Map"
                assert "CC BY 4.0" in row["license_info"]

                # Second sync of identical payload must count duplicate instead of duplicating row
                second = sync_openchargemap_stations(api_key="test-key-123")
                assert second["ok"] is True
                assert second["imported"] == 0
                assert second["duplicates"] >= 1
    finally:
        execute("DELETE FROM Stations WHERE external_source_id = 'OCM-777001'")


def test_nominatim_explicit_geocode_and_reverse_via_api(app, client):
    search_resp = MagicMock(status_code=200)
    search_resp.json.return_value = [
        {
            "display_name": "Connaught Place, New Delhi, Delhi, 110001, India",
            "lat": "28.6315",
            "lon": "77.2167",
            "category": "place",
            "type": "suburb",
            "address": {"city": "New Delhi", "state": "Delhi", "postcode": "110001"},
        }
    ]
    rev_resp = MagicMock(status_code=200)
    rev_resp.json.return_value = {
        "display_name": "15 Janpath Road, New Delhi, 110001, India",
        "address": {"city": "New Delhi", "state": "Delhi", "postcode": "110001", "country": "India"},
    }

    execute("DELETE FROM ApiCache WHERE provider = 'Nominatim'")
    with app.app_context():
        with patch("app.services.http_client.requests.get", return_value=search_resp):
            r = client.get("/api/geo/search?q=Connaught%20Place%20Test")
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"] is True
            assert data["results"][0]["postcode"] == "110001"
            assert "OpenStreetMap" in data["attribution"]

        # Reject short keystroke fragment (<3 chars)
        r_short = client.get("/api/geo/search?q=CP")
        assert r_short.status_code == 400

        with patch("app.services.http_client.requests.get", return_value=rev_resp):
            r2 = client.get("/api/geo/reverse?lat=28.62&lng=77.21")
            assert r2.status_code == 200
            assert r2.get_json()["postcode"] == "110001"

    execute("DELETE FROM ApiCache WHERE provider = 'Nominatim'")


def test_osrm_route_polyline_and_haversine_fallback(app, client):
    osrm_ok = MagicMock(status_code=200)
    osrm_ok.json.return_value = {
        "code": "Ok",
        "routes": [
            {
                "distance": 4520.0,
                "duration": 610.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[77.2090, 28.6139], [77.2190, 28.6300]],
                },
                "legs": [
                    {
                        "steps": [
                            {"name": "Janpath Road", "distance": 900, "maneuver": {"type": "turn", "modifier": "left"}}
                        ]
                    }
                ],
            }
        ],
    }

    execute("DELETE FROM ApiCache WHERE provider = 'OSRM'")
    with app.app_context():
        with patch("app.services.http_client.requests.get", return_value=osrm_ok):
            r = client.get("/api/geo/route?origin_lat=28.6139&origin_lng=77.2090&dest_lat=28.6300&dest_lng=77.2190")
            assert r.status_code == 200
            body = r.get_json()
            assert body["ok"] is True
            assert body["fallback_mode"] is False
            assert body["distance_km"] == 4.52
            assert body["duration_min"] == 10
            assert len(body["geometry"]["coordinates"]) == 2

        # Different coordinates with OSRM timeout -> clean Haversine fallback
        osrm_down = MagicMock(status_code=503, text="Down", reason="Unavailable")
        with patch("app.services.http_client.requests.get", return_value=osrm_down):
            r_fb = client.get("/api/geo/route?origin_lat=28.5000&origin_lng=77.1000&dest_lat=28.6300&dest_lng=77.2190")
            assert r_fb.status_code == 200
            fb_body = r_fb.get_json()
            assert fb_body["ok"] is True
            assert fb_body["fallback_mode"] is True
            assert fb_body["straight_line_km"] > 5

        r_near = client.get("/api/stations/nearby?lat=28.6139&lng=77.2090&radius_km=50")
        assert r_near.status_code == 200
        assert r_near.get_json()["count"] >= 1

    execute("DELETE FROM ApiCache WHERE provider = 'OSRM'")


def test_open_meteo_weather_endpoint(app, client):
    meteo_ok = MagicMock(status_code=200)
    meteo_ok.json.return_value = {
        "current": {
            "time": "2026-11-12T20:00",
            "temperature_2m": 24.5,
            "relative_humidity_2m": 52,
            "weather_code": 1,
            "wind_speed_10m": 8.2,
            "precipitation": 0.0,
        },
        "hourly": {
            "time": ["2026-11-12T20:00", "2026-11-12T21:00", "2026-11-12T22:00"],
            "temperature_2m": [24.5, 23.1, 21.8],
            "precipitation_probability": [5, 10, 15],
            "weather_code": [1, 2, 2],
        },
    }

    execute("DELETE FROM ApiCache WHERE provider = 'OpenMeteo'")
    with app.app_context():
        with patch("app.services.http_client.requests.get", return_value=meteo_ok):
            r = client.get("/api/weather?lat=28.6139&lng=77.2090")
            assert r.status_code == 200
            body = r.get_json()
            assert body["ok"] is True
            assert body["current"]["temperature_c"] == 24.5
            assert body["current"]["condition"] == "Mainly clear"
            assert "Open-Meteo" in body["attribution"]
            assert len(body["hourly_forecast"]) >= 2

    execute("DELETE FROM ApiCache WHERE provider = 'OpenMeteo'")


def test_indian_pincode_multi_post_office_and_validation(app, client):
    pin_resp = MagicMock(status_code=200)
    pin_resp.json.return_value = [
        {
            "Message": "Number of pincode(s) found:2",
            "Status": "Success",
            "PostOffice": [
                {
                    "Name": "Connaught Place",
                    "BranchType": "Sub Post Office",
                    "DeliveryStatus": "Delivery",
                    "District": "Central Delhi",
                    "Division": "New Delhi Central",
                    "Region": "Delhi",
                    "Block": "New Delhi",
                    "State": "Delhi",
                },
                {
                    "Name": "Janpath",
                    "BranchType": "Sub Post Office",
                    "DeliveryStatus": "Non-Delivery",
                    "District": "New Delhi",
                    "Division": "New Delhi Central",
                    "Region": "Delhi",
                    "Block": "New Delhi",
                    "State": "Delhi",
                },
            ],
        }
    ]

    execute("DELETE FROM ApiCache WHERE provider = 'PostalPinCode'")
    with app.app_context():
        bad = client.get("/api/pincode/012345")
        assert bad.status_code == 400
        assert bad.get_json()["valid"] is False

        with patch("app.services.http_client.requests.get", return_value=pin_resp):
            ok = client.get("/api/pincode/110001")
            assert ok.status_code == 200
            body = ok.get_json()
            assert body["ok"] is True
            assert body["state"] == "Delhi"
            assert body["post_office_count"] == 2
            assert "multiple Post Offices" in body["disclaimer"]

    execute("DELETE FROM ApiCache WHERE provider = 'PostalPinCode'")


def test_charging_point_qr_lifecycle_and_rotation(app, client, admin_client):
    pt_row = query_one("SELECT point_id FROM ChargingPoints LIMIT 1")
    assert pt_row is not None
    point_id = pt_row["point_id"]

    # Admin can fetch dispenser PNG QR
    png_res = admin_client.get(f"/admin/points/{point_id}/qr.png")
    assert png_res.status_code == 200
    assert png_res.mimetype == "image/png"
    assert png_res.data[:4] == b"\x89PNG"

    qr_row = query_one(
        "SELECT qr_token, scan_count FROM PointQRCodes WHERE point_id = %s AND qr_status = 'ACTIVE' ORDER BY qr_id DESC LIMIT 1",
        (point_id,),
    )
    old_token = qr_row["qr_token"]

    # Scanning point QR increments count and renders non-payment identification notice
    scan_res = client.get(f"/qr/point/{old_token}")
    assert scan_res.status_code == 200
    assert b"Charging Point Identification" in scan_res.data
    assert b"never marks a payment completed" in scan_res.data

    # Rotate token -> old token revoked (410 Gone)
    rot_res = admin_client.post(f"/admin/points/{point_id}/qr/regenerate", follow_redirects=False)
    assert rot_res.status_code == 302
    revoked_res = client.get(f"/qr/point/{old_token}")
    assert revoked_res.status_code == 410


def test_booking_qr_rbac_and_admin_checkin(app, client, owner_client, admin_client):
    booking = query_one("SELECT booking_id, user_id FROM Bookings WHERE user_id = 2 LIMIT 1")
    assert booking is not None
    bid = booking["booking_id"]

    # Owning driver (user_id=2) can view /owner/bookings and download their Booking QR PNG
    page = owner_client.get("/owner/bookings")
    assert page.status_code == 200
    assert b"Booking Check-In Verification QRs" in page.data

    png_res = owner_client.get(f"/owner/bookings/{bid}/qr.png")
    assert png_res.status_code == 200
    assert png_res.data[:4] == b"\x89PNG"

    bqr = query_one("SELECT qr_token, qr_status FROM BookingQRCodes WHERE booking_id = %s", (bid,))
    token = bqr["qr_token"]

    # Different owner (user_id=3) is forbidden (403) from PNG & scan page
    other_owner = app.test_client()
    with other_owner.session_transaction() as sess:
        sess["user_id"] = 3
        sess["role"] = "OWNER"
    assert other_owner.get(f"/owner/bookings/{bid}/qr.png").status_code == 403
    assert other_owner.get(f"/qr/booking/{token}").status_code == 403

    # Owning driver can open check-in pass view, cannot trigger admin checkin POST
    assert owner_client.get(f"/qr/booking/{token}").status_code == 200
    assert owner_client.post(f"/qr/booking/{token}/checkin").status_code == 403

    # Restore original status after verifying admin access cleanly
    assert admin_client.get(f"/qr/booking/{token}").status_code == 200


def test_admin_api_health_observability_and_4way_provenance_views(client, admin_client, owner_client):
    # Admin dashboard displays API integration health & A/B/C/D provenance breakdown
    dash = admin_client.get("/admin/dashboard")
    assert dash.status_code == 200
    assert b"External API Integration Health" in dash.data
    assert b"A. Official Company Disclosures" in dash.data
    assert b"B. Third-Party Charging" in dash.data
    assert b"ChargeAlong API" in dash.data

    # Public & Admin Data Sources show 4-way provenance separation
    pub_ds = client.get("/data-sources")
    assert pub_ds.status_code == 200
    assert b"A. Official Company Disclosures" in pub_ds.data
    assert b"D. Simulated Charging" in pub_ds.data

    adm_ds = admin_client.get("/admin/data-sources")
    assert adm_ds.status_code == 200
    assert b"Sync Open Charge Map" in adm_ds.data

    # Station detail page includes geo_weather JS and provenance metadata
    st_row = query_one("SELECT station_id FROM Stations WHERE approval_status = 'APPROVED' AND latitude IS NOT NULL LIMIT 1")
    detail = client.get(f"/stations/{st_row['station_id']}")
    assert detail.status_code == 200
    assert b"ev_geo_weather.js" in detail.data

    # Non-admin owner cannot trigger OCM sync route
    assert owner_client.post("/admin/integrations/ocm/sync").status_code == 403
