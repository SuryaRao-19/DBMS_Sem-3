"""
Stations and Charging Points Service
EV Charging Station Management System - Optimized Geospatial, Provenance & NCR Queries
"""
import re
import uuid
import os
import json
from app.db import query_all, query_one, execute
from app.services.audit_service import log_audit_event

_SEED_CACHE = None


def _get_seed_data():
    """Load curated verified authentic Tata Power NCR stations when database is unavailable."""
    global _SEED_CACHE
    if _SEED_CACHE is not None:
        return _SEED_CACHE
    seed_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "data",
        "seed_stations.json"
    )
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as fh:
                _SEED_CACHE = json.load(fh)
                return _SEED_CACHE
        except Exception:
            pass
    return {"stations": [], "points": [], "metrics": {}}


def _filter_seed_stations(
    city=None,
    status=None,
    operator=None,
    connector=None,
    min_power=None,
    max_power=None,
    only_approved=True,
    **kwargs,
):
    """Filter in-memory authentic station dataset when live database is unreachable."""
    seed = _get_seed_data()
    stations = seed.get("stations", [])
    results = []
    search_term = kwargs.get("search") or kwargs.get("q")
    if search_term:
        search_term = str(search_term).strip().lower()

    for s in stations:
        item = dict(s)
        if only_approved and item.get("approval_status") != "APPROVED":
            continue
        if city and str(city).strip() and (item.get("city") or "").lower() != str(city).strip().lower():
            continue
        if status and str(status).strip() and (item.get("station_status") or "").upper() != str(status).strip().upper():
            continue
        if operator and str(operator).strip() and str(operator).strip().lower() not in (item.get("operator_name") or "").lower():
            continue
        if connector and str(connector).strip():
            conn_str = str(connector).strip().upper()
            st_conn = (item.get("connector_types") or "").upper()
            if conn_str not in st_conn:
                continue
        if min_power is not None and str(min_power).strip():
            try:
                min_p = float(min_power)
                cap_str = str(item.get("charger_capacity_kw") or "0").split()[0].replace("kW", "")
                cap = float(cap_str)
                if cap < min_p and float(item.get("peak_power_kw") or 0) < min_p:
                    continue
            except (ValueError, TypeError):
                pass
        if max_power is not None and str(max_power).strip():
            try:
                max_p = float(max_power)
                cap_str = str(item.get("charger_capacity_kw") or "0").split()[0].replace("kW", "")
                cap = float(cap_str)
                if cap > max_p and float(item.get("peak_power_kw") or 0) > max_p:
                    continue
            except (ValueError, TypeError):
                pass
        if search_term:
            haystack = f"{item.get('station_name') or ''} {item.get('address') or ''} {item.get('locality') or ''} {item.get('city') or ''} {item.get('postal_code') or ''}".lower()
            if search_term not in haystack:
                continue
        results.append(item)
    return results


VALID_STATION_VERIFICATION_STATUSES = (
    "VERIFIED",
    "PENDING_VERIFICATION",
    "PENDING_REVIEW",
    "HISTORICAL",
    "DEMO",
    "ESTIMATED",
    "UNAVAILABLE",
    "OUTDATED",
)


def _slugify(name):
    """Build URL-safe station slug without exposing database IDs."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "station").lower()).strip("-")
    return base[:140] or f"station-{uuid.uuid4().hex[:6]}"


def get_all_stations(
    city=None,
    status=None,
    operator=None,
    connector=None,
    min_power=None,
    max_power=None,
    only_approved=True,
    **kwargs,
):
    """
    Retrieve stations with optional city, operational status, operator, connector,
    capacity bounds, and approval filtering.
    Uses aggregated joins to avoid N+1 queries and surfaces geospatial/operator/provenance metadata.
    """
    sql = (
        "SELECT s.station_id, s.station_name, s.station_slug, s.address, s.locality, "
        "       s.city, s.state, s.postal_code, s.country, "
        "       s.latitude, s.longitude, s.google_place_id, s.maps_url, "
        "       s.operator_name, s.connector_types, s.charger_capacity_kw, s.charger_type, s.gun_count, "
        "       s.contact_info, s.opening_time, s.closing_time, s.station_status, "
        "       s.verification_status, s.approval_status, s.source_url, s.source_type, s.source_name, "
        "       s.published_at, s.retrieved_at, s.last_verified_at, s.confidence_level, s.record_origin, "
        "       s.is_demo, s.created_at, "
        "       COUNT(cp.point_id) AS total_points, "
        "       COALESCE(SUM(CASE WHEN cp.point_status = 'AVAILABLE' THEN 1 ELSE 0 END), 0) AS available_points, "
        "       COALESCE(SUM(CASE WHEN cp.point_status = 'OCCUPIED' THEN 1 ELSE 0 END), 0) AS occupied_points, "
        "       COALESCE(MAX(cp.max_power_kw), 0) AS peak_power_kw, "
        "       (SELECT GROUP_CONCAT(sf.facility_name ORDER BY sf.facility_name SEPARATOR ', ') "
        "        FROM StationFacilities sf WHERE sf.station_id = s.station_id) AS facilities_csv "
        "FROM Stations s "
        "LEFT JOIN ChargingPoints cp ON cp.station_id = s.station_id "
        "WHERE 1=1"
    )
    params = []
    if only_approved:
        sql += " AND s.approval_status = 'APPROVED'"
    if city and str(city).strip():
        sql += " AND s.city = %s"
        params.append(str(city).strip())
    if status and str(status).strip():
        sql += " AND s.station_status = %s"
        params.append(str(status).strip())
    if operator and str(operator).strip():
        sql += " AND s.operator_name = %s"
        params.append(str(operator).strip())
    if connector and str(connector).strip():
        conn_str = str(connector).strip().upper()
        sql += " AND (s.connector_types LIKE %s OR cp.connector_type = %s)"
        params.extend([f"%{conn_str}%", conn_str])
    if min_power is not None and str(min_power).strip():
        try:
            min_p = float(min_power)
            sql += " AND (s.charger_capacity_kw >= %s OR cp.max_power_kw >= %s)"
            params.extend([min_p, min_p])
        except (ValueError, TypeError):
            pass
    if max_power is not None and str(max_power).strip():
        try:
            max_p = float(max_power)
            sql += " AND (s.charger_capacity_kw <= %s OR cp.max_power_kw <= %s)"
            params.extend([max_p, max_p])
        except (ValueError, TypeError):
            pass
    search_term = kwargs.get("search") or kwargs.get("q")
    if search_term and str(search_term).strip():
        term = f"%{str(search_term).strip()}%"
        sql += " AND (s.station_name LIKE %s OR s.address LIKE %s OR s.locality LIKE %s OR s.city LIKE %s)"
        params.extend([term, term, term, term])

    sql += (
        " GROUP BY s.station_id, s.station_name, s.station_slug, s.address, s.locality, "
        "          s.city, s.state, s.postal_code, s.country, "
        "          s.latitude, s.longitude, s.google_place_id, s.maps_url, "
        "          s.operator_name, s.connector_types, s.charger_capacity_kw, s.charger_type, s.gun_count, "
        "          s.contact_info, s.opening_time, s.closing_time, s.station_status, "
        "          s.verification_status, s.approval_status, s.source_url, s.source_type, s.source_name, "
        "          s.published_at, s.retrieved_at, s.last_verified_at, s.confidence_level, s.record_origin, "
        "          s.is_demo, s.created_at "
        " ORDER BY (s.latitude IS NULL), s.city, s.station_name"
    )
    try:
        stations = query_all(sql, params)
    except Exception:
        return _filter_seed_stations(
            city=city,
            status=status,
            operator=operator,
            connector=connector,
            min_power=min_power,
            max_power=max_power,
            only_approved=only_approved,
            **kwargs,
        )

    for s in stations:
        if s.get("opening_time") is not None:
            s["opening_time"] = str(s["opening_time"])
        if s.get("closing_time") is not None:
            s["closing_time"] = str(s["closing_time"])
        s["latitude"] = float(s["latitude"]) if s.get("latitude") is not None else None
        s["longitude"] = float(s["longitude"]) if s.get("longitude") is not None else None
        s["total_points"] = int(s["total_points"] or 0)
        s["available_points"] = int(s["available_points"] or 0)
        s["occupied_points"] = int(s["occupied_points"] or 0)
        s["peak_power_kw"] = float(s["peak_power_kw"] or 0)
        s["status"] = s.get("station_status")
        s["facilities_list"] = [f.strip() for f in (s.get("facilities_csv") or "").split(",") if f.strip()]

    return stations


def _hydrate_station(station):
    """Attach normalized strings, coordinates, points, and facilities onto a single station dict."""
    if not station:
        return None
    if station.get("opening_time") is not None:
        station["opening_time"] = str(station["opening_time"])
    if station.get("closing_time") is not None:
        station["closing_time"] = str(station["closing_time"])
    station["latitude"] = float(station["latitude"]) if station.get("latitude") is not None else None
    station["longitude"] = float(station["longitude"]) if station.get("longitude") is not None else None
    station["points"] = query_all(
        "SELECT point_id, station_id, point_code, connector_type, max_power_kw, "
        "       tariff_per_kwh, point_status, created_at "
        "FROM ChargingPoints WHERE station_id = %s ORDER BY point_code",
        (station["station_id"],)
    )
    facs = query_all(
        "SELECT facility_name FROM StationFacilities WHERE station_id = %s ORDER BY facility_name",
        (station["station_id"],)
    )
    station["facilities_list"] = [f["facility_name"] for f in facs]
    return station


def get_station_by_id(station_id, only_approved=True):
    """Retrieve single station with its charging points, provenance metadata, and facilities."""
    sql = (
        "SELECT station_id, station_name, station_slug, address, locality, city, state, postal_code, country, "
        "       latitude, longitude, google_place_id, maps_url, "
        "       operator_name, connector_types, charger_capacity_kw, charger_type, gun_count, contact_info, "
        "       opening_time, closing_time, station_status, "
        "       verification_status, approval_status, source_url, source_type, source_name, "
        "       published_at, retrieved_at, last_verified_at, confidence_level, record_origin, is_demo, created_at "
        "FROM Stations WHERE station_id = %s"
    )
    if only_approved:
        sql += " AND approval_status = 'APPROVED'"
    try:
        return _hydrate_station(query_one(sql, (station_id,)))
    except Exception:
        seed = _get_seed_data()
        for s in seed.get("stations", []):
            if int(s.get("station_id") or 0) == int(station_id):
                if only_approved and s.get("approval_status") != "APPROVED":
                    return None
                st_copy = dict(s)
                st_copy["points"] = [p for p in seed.get("points", []) if int(p.get("station_id") or 0) == int(station_id)]
                st_copy["facilities_list"] = list(st_copy.get("facilities_list") or [])
                return st_copy
        return None


def get_station_by_slug(slug, only_approved=True):
    """Retrieve single station cleanly via its public URL slug."""
    sql = (
        "SELECT station_id, station_name, station_slug, address, locality, city, state, postal_code, country, "
        "       latitude, longitude, google_place_id, maps_url, "
        "       operator_name, connector_types, charger_capacity_kw, charger_type, gun_count, contact_info, "
        "       opening_time, closing_time, station_status, "
        "       verification_status, approval_status, source_url, source_type, source_name, "
        "       published_at, retrieved_at, last_verified_at, confidence_level, record_origin, is_demo, created_at "
        "FROM Stations WHERE station_slug = %s"
    )
    if only_approved:
        sql += " AND approval_status = 'APPROVED'"
    try:
        return _hydrate_station(query_one(sql, (slug.strip(),)))
    except Exception:
        seed = _get_seed_data()
        target_slug = slug.strip().lower()
        for s in seed.get("stations", []):
            if (s.get("station_slug") or "").lower() == target_slug:
                if only_approved and s.get("approval_status") != "APPROVED":
                    return None
                st_copy = dict(s)
                st_id = int(st_copy.get("station_id") or 0)
                st_copy["points"] = [p for p in seed.get("points", []) if int(p.get("station_id") or 0) == st_id]
                st_copy["facilities_list"] = list(st_copy.get("facilities_list") or [])
                return st_copy
        return None


def verify_station_record(station_id, new_status, admin_user_id):
    """Admin action: transition station verification_status (VERIFIED / HISTORICAL / OUTDATED / PENDING_VERIFICATION) with audit log."""
    norm = (new_status or "").strip().upper()
    if norm not in VALID_STATION_VERIFICATION_STATUSES:
        return False, f"Invalid verification status '{new_status}'."
    row = query_one("SELECT station_id, station_name, verification_status, latitude, longitude FROM Stations WHERE station_id = %s", (station_id,))
    if not row:
        return False, "Station not found."
    if norm == "VERIFIED" and (row.get("latitude") is None or row.get("longitude") is None):
        return False, "Cannot mark VERIFIED without grounded latitude and longitude coordinates."

    execute(
        "UPDATE Stations SET verification_status = %s, last_verified_at = NOW() WHERE station_id = %s",
        (norm, station_id),
    )
    log_audit_event(
        action="STATION_VERIFICATION_UPDATED",
        entity_name="Stations",
        entity_id=station_id,
        user_id=admin_user_id,
        details=f"Station '{row['station_name']}' verification_status changed from {row['verification_status']} to {norm}",
    )
    return True, f"{row['station_name']} marked as {norm}."


def create_station(
    station_name,
    address,
    city,
    opening_time="06:00:00",
    closing_time="23:00:00",
    status="ACTIVE",
    state="Delhi NCR",
    postal_code=None,
    latitude=None,
    longitude=None,
    operator_name="Tata Power EZ Charge",
    connector_types=None,
    charger_capacity_kw=None,
    maps_url=None,
    source_url=None,
    verification_status="DEMO",
    approval_status="APPROVED",
):
    """Create a new charging station with optional geospatial & verification fields."""
    if latitude is not None and longitude is not None and not maps_url:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={float(latitude):.6f},{float(longitude):.6f}"

    slug = _slugify(station_name)
    if query_one("SELECT station_id FROM Stations WHERE station_slug = %s", (slug,)):
        slug = f"{slug[:130]}-{uuid.uuid4().hex[:5]}"

    return execute(
        "INSERT INTO Stations ("
        "  station_name, station_slug, address, city, state, postal_code, latitude, longitude, maps_url, "
        "  operator_name, connector_types, charger_capacity_kw, opening_time, closing_time, "
        "  station_status, verification_status, approval_status, source_url, last_verified_at"
        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
        (
            station_name.strip(),
            slug,
            address.strip(),
            city.strip(),
            (state or "Delhi NCR").strip(),
            postal_code.strip() if postal_code else None,
            latitude,
            longitude,
            maps_url,
            (operator_name or "Tata Power EZ Charge").strip(),
            connector_types,
            charger_capacity_kw,
            opening_time,
            closing_time,
            status,
            verification_status,
            approval_status,
            source_url,
        )
    )


def update_station(
    station_id,
    station_name,
    address,
    city,
    opening_time,
    closing_time,
    status,
    state=None,
    postal_code=None,
    latitude=None,
    longitude=None,
    operator_name=None,
    verification_status=None,
):
    """Update station details, location metadata, and operational status."""
    fields = [
        "station_name = %s",
        "address = %s",
        "city = %s",
        "opening_time = %s",
        "closing_time = %s",
        "station_status = %s",
    ]
    params = [
        station_name.strip(),
        address.strip(),
        city.strip(),
        opening_time,
        closing_time,
        status,
    ]
    if state is not None:
        fields.append("state = %s")
        params.append(state.strip())
    if postal_code is not None:
        fields.append("postal_code = %s")
        params.append(postal_code.strip() or None)
    if latitude is not None and longitude is not None:
        fields.append("latitude = %s")
        fields.append("longitude = %s")
        fields.append("maps_url = %s")
        params.extend([latitude, longitude, f"https://www.google.com/maps/search/?api=1&query={float(latitude):.6f},{float(longitude):.6f}"])
    if operator_name is not None:
        fields.append("operator_name = %s")
        params.append(operator_name.strip())
    if verification_status is not None:
        fields.append("verification_status = %s")
        params.append(verification_status)

    params.append(station_id)
    execute(f"UPDATE Stations SET {', '.join(fields)} WHERE station_id = %s", params)


def get_all_charging_points(station_id=None, only_approved=True):
    """Retrieve all charging dispensers with their parent station info."""
    sql = (
        "SELECT cp.point_id, cp.station_id, cp.point_code, cp.connector_type, "
        "       cp.max_power_kw, cp.tariff_per_kwh, cp.point_status, cp.created_at, "
        "       s.station_name, s.city, s.state, s.station_status, s.operator_name, "
        "       s.latitude, s.longitude, s.approval_status "
        "FROM ChargingPoints cp "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE 1=1"
    )
    params = []
    if only_approved:
        sql += " AND s.approval_status = 'APPROVED'"
    if station_id is not None:
        sql += " AND cp.station_id = %s"
        params.append(station_id)
    sql += " ORDER BY s.station_name, cp.point_code"
    try:
        return query_all(sql, params)
    except Exception:
        seed = _get_seed_data()
        pts = seed.get("points", [])
        if station_id is not None:
            pts = [p for p in pts if int(p.get("station_id") or 0) == int(station_id)]
        if only_approved:
            pts = [p for p in pts if p.get("approval_status") == "APPROVED"]
        return [dict(p) for p in pts]


def create_charging_point(station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status="AVAILABLE"):
    """Add a new dispenser to a station."""
    return execute(
        "INSERT INTO ChargingPoints (station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (station_id, point_code.strip().upper(), connector_type, float(max_power_kw), float(tariff_per_kwh), point_status)
    )


def update_charging_point(point_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status):
    """Update a dispenser's parameters and live status."""
    execute(
        "UPDATE ChargingPoints SET point_code = %s, connector_type = %s, max_power_kw = %s, "
        "tariff_per_kwh = %s, point_status = %s WHERE point_id = %s",
        (point_code.strip().upper(), connector_type, float(max_power_kw), float(tariff_per_kwh), point_status, point_id)
    )


def get_point_by_id(point_id):
    """Get details of a single charging point with station info."""
    try:
        return query_one(
            "SELECT cp.*, s.station_name, s.address, s.city, s.state, s.postal_code, "
            "       s.operator_name, s.latitude, s.longitude, s.maps_url, s.verification_status "
            "FROM ChargingPoints cp JOIN Stations s ON s.station_id = cp.station_id "
            "WHERE cp.point_id = %s",
            (point_id,)
        )
    except Exception:
        seed = _get_seed_data()
        for p in seed.get("points", []):
            if int(p.get("point_id") or 0) == int(point_id):
                return dict(p)
        return None
