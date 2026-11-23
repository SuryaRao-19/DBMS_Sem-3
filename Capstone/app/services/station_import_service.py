"""
CSV Station Data Import, Validation & Admin Approval Workflow
EV Charging Station Management System
"""
import csv
import io
import re
from urllib.parse import urlparse
from app.db import query_all, query_one, execute, transaction

_PIN_RE = re.compile(r"^\d{6}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


def _validate_http_url(url_val):
    if not url_val:
        return False
    parsed = urlparse(url_val.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _normalize_time(val, default_val):
    raw = (val or "").strip()
    if not raw:
        return default_val
    if not _TIME_RE.match(raw):
        return None
    return raw if len(raw) == 8 else f"{raw}:00"


def validate_station_record(raw_row):
    """
    Validate a single imported/submitted station dictionary.
    Returns (cleaned_dict, error_message).
    """
    name = (raw_row.get("station_name") or "").strip()
    address = (raw_row.get("address") or "").strip()
    city = (raw_row.get("city") or "").strip()
    state = (raw_row.get("state") or "Delhi NCR").strip()
    postal_code = (raw_row.get("postal_code") or "").strip()
    operator_name = (raw_row.get("operator_name") or "").strip()
    connector_types = (raw_row.get("connector_types") or "").strip()
    capacity_kw = (raw_row.get("charger_capacity_kw") or "").strip()
    source_url = (raw_row.get("source_url") or "").strip()
    maps_url = (raw_row.get("maps_url") or "").strip()
    contact_info = (raw_row.get("contact_info") or "").strip()
    facilities_raw = (raw_row.get("facilities") or "").strip()

    if len(name) < 3 or len(name) > 120:
        return None, "Station name must be 3–120 characters."
    if len(address) < 5 or len(address) > 255:
        return None, f"Address is too short or invalid for '{name}'."
    if len(city) < 2 or len(city) > 80:
        return None, f"City is required for '{name}'."
    if not _PIN_RE.match(postal_code):
        return None, f"Postal code must be a valid 6-digit Indian PIN code for '{name}' (got '{postal_code}')."
    if len(operator_name) < 2:
        return None, f"Charging operator name is required for '{name}'."

    try:
        lat = float(raw_row.get("latitude"))
        lng = float(raw_row.get("longitude"))
    except (TypeError, ValueError):
        return None, f"Invalid latitude/longitude coordinates for '{name}'."

    # Enforce realistic Indian geographical coordinate bounding box (lat 6–38 N, lng 68–98 E)
    if not (6.0 <= lat <= 38.0 and 68.0 <= lng <= 98.0):
        return None, f"Coordinates ({lat}, {lng}) for '{name}' fall outside India geographic bounds."

    if not _validate_http_url(source_url):
        return None, f"Valid http/https source_url is required for '{name}'."

    if maps_url and not _validate_http_url(maps_url):
        return None, f"Invalid maps_url for '{name}'."
    if not maps_url:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lng:.6f}"

    open_t = _normalize_time(raw_row.get("opening_time"), "06:00:00")
    close_t = _normalize_time(raw_row.get("closing_time"), "23:00:00")
    if open_t is None or close_t is None:
        return None, f"Invalid opening/closing time format (expected HH:MM or HH:MM:SS) for '{name}'."

    facilities = [f.strip() for f in facilities_raw.split(";") if f.strip()] if facilities_raw else []
    if not facilities and "," in facilities_raw:
        facilities = [f.strip() for f in facilities_raw.split(",") if f.strip()]

    return {
        "station_name": name,
        "address": address,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "latitude": round(lat, 7),
        "longitude": round(lng, 7),
        "maps_url": maps_url,
        "operator_name": operator_name,
        "connector_types": connector_types or "CCS2",
        "charger_capacity_kw": capacity_kw or "30 kW DC",
        "contact_info": contact_info or None,
        "opening_time": open_t,
        "closing_time": close_t,
        "source_url": source_url,
        "facilities": facilities[:10],
    }, None


def _is_duplicate_station(cleaned):
    """Detect duplicates by station name, address+PIN, or close GPS coordinate proximity (~50m)."""
    by_name = query_one(
        "SELECT station_id FROM Stations WHERE LOWER(station_name) = LOWER(%s) LIMIT 1",
        (cleaned["station_name"],),
    )
    if by_name:
        return f"Duplicate station name '{cleaned['station_name']}' (matches ID #{by_name['station_id']})."

    by_addr = query_one(
        "SELECT station_id FROM Stations WHERE postal_code = %s AND LOWER(address) = LOWER(%s) LIMIT 1",
        (cleaned["postal_code"], cleaned["address"]),
    )
    if by_addr:
        return f"Duplicate address + PIN '{cleaned['postal_code']}' (matches ID #{by_addr['station_id']})."

    by_geo = query_one(
        "SELECT station_id, station_name FROM Stations "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL "
        "  AND ABS(latitude - %s) < 0.00045 AND ABS(longitude - %s) < 0.00045 LIMIT 1",
        (cleaned["latitude"], cleaned["longitude"]),
    )
    if by_geo:
        return f"Coordinate proximity duplicate (~50m) of existing hub '{by_geo['station_name']}'."

    return None


def import_stations_from_csv(csv_text, approve_immediately=False):
    """
    Parse and import charging stations from CSV text.
    New records default to approval_status='PENDING_APPROVAL' and verification_status='PENDING_REVIEW'
    so unverified records require admin sign-off before public listing.
    Returns summary dict: {imported_ids, skipped, errors}.
    """
    if not csv_text or not csv_text.strip():
        return {"imported_ids": [], "skipped": [], "errors": ["CSV payload is empty."]}

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        return {"imported_ids": [], "skipped": [], "errors": ["CSV header row is missing."]}

    required_cols = {"station_name", "address", "city", "postal_code", "latitude", "longitude", "operator_name", "source_url"}
    missing_cols = required_cols - {c.strip() for c in reader.fieldnames if c}
    if missing_cols:
        return {
            "imported_ids": [],
            "skipped": [],
            "errors": [f"Missing required CSV columns: {', '.join(sorted(missing_cols))}"],
        }

    imported_ids = []
    skipped = []
    errors = []

    approval_val = "APPROVED" if approve_immediately else "PENDING_APPROVAL"
    verif_val = "VERIFIED" if approve_immediately else "PENDING_REVIEW"

    for idx, row in enumerate(reader, start=2):
        cleaned, val_err = validate_station_record(row)
        if val_err:
            errors.append(f"Row {idx}: {val_err}")
            continue

        dup_err = _is_duplicate_station(cleaned)
        if dup_err:
            skipped.append(f"Row {idx}: {dup_err}")
            continue

        with transaction() as cur:
            cur.execute(
                "INSERT INTO Stations ("
                "  station_name, address, city, state, postal_code, latitude, longitude, maps_url, "
                "  operator_name, connector_types, charger_capacity_kw, contact_info, "
                "  opening_time, closing_time, station_status, verification_status, approval_status, "
                "  source_url, last_verified_at"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, NOW())",
                (
                    cleaned["station_name"],
                    cleaned["address"],
                    cleaned["city"],
                    cleaned["state"],
                    cleaned["postal_code"],
                    cleaned["latitude"],
                    cleaned["longitude"],
                    cleaned["maps_url"],
                    cleaned["operator_name"],
                    cleaned["connector_types"],
                    cleaned["charger_capacity_kw"],
                    cleaned["contact_info"],
                    cleaned["opening_time"],
                    cleaned["closing_time"],
                    verif_val,
                    approval_val,
                    cleaned["source_url"],
                ),
            )
            st_id = cur.lastrowid
            for fac in cleaned["facilities"]:
                cur.execute(
                    "INSERT IGNORE INTO StationFacilities (station_id, facility_name) VALUES (%s, %s)",
                    (st_id, fac[:80]),
                )
            imported_ids.append(st_id)

    return {"imported_ids": imported_ids, "skipped": skipped, "errors": errors}


def review_station_approval(station_id, decision, verification_status=None):
    """Admin review gate: approve or reject a station before public map/directory publishing."""
    decision_norm = (decision or "").strip().upper()
    if decision_norm not in ("APPROVED", "REJECTED", "PENDING_APPROVAL"):
        return False, f"Invalid approval decision '{decision}'."

    station = query_one("SELECT station_id, station_name, source_url FROM Stations WHERE station_id = %s", (station_id,))
    if not station:
        return False, "Station not found."

    if verification_status:
        verif_norm = verification_status.strip().upper()
    elif decision_norm == "APPROVED":
        verif_norm = "VERIFIED" if station.get("source_url") else "DEMO"
    else:
        verif_norm = "PENDING_REVIEW"

    execute(
        "UPDATE Stations SET approval_status = %s, verification_status = %s, last_verified_at = NOW() WHERE station_id = %s",
        (decision_norm, verif_norm, station_id),
    )
    return True, f"Station '{station['station_name']}' marked {decision_norm} ({verif_norm})."


def get_pending_approval_stations():
    """Fetch stations awaiting admin verification/approval."""
    return query_all(
        "SELECT station_id, station_name, address, city, state, postal_code, latitude, longitude, "
        "       operator_name, source_url, verification_status, approval_status, created_at "
        "FROM Stations WHERE approval_status != 'APPROVED' ORDER BY created_at DESC"
    )

