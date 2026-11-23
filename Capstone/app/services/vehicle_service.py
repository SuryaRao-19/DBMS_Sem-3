"""
Vehicle Management Service
EV Charging Station Management System - Production Hardened
"""
from app.db import query_all, query_one, execute, transaction

VALID_VEHICLE_CATEGORIES = ("2W", "3W", "4W_SUV", "4W_SEDAN", "FLEET_BUS", "COMMERCIAL")
VALID_CONNECTOR_TYPES = ("TYPE2", "CCS2", "CHADEMO", "GB_T")


def get_vehicles_by_user(user_id):
    """Retrieve all vehicles owned by a specific EV customer, default vehicle first."""
    try:
        return query_all(
            "SELECT * FROM Vehicles WHERE user_id = %s ORDER BY is_default DESC, created_at DESC",
            (user_id,)
        )
    except Exception:
        return []


def get_vehicle_by_id(vehicle_id, user_id=None):
    """Retrieve single vehicle, enforcing user ownership if user_id is passed."""
    sql = "SELECT * FROM Vehicles WHERE vehicle_id = %s"
    params = [vehicle_id]
    if user_id:
        sql += " AND user_id = %s"
        params.append(user_id)
    try:
        return query_one(sql, params)
    except Exception:
        return None


def add_vehicle(
    user_id,
    registration_no,
    make,
    model,
    battery_capacity_kwh,
    vehicle_category="4W_SUV",
    connector_type="CCS2",
    registration_year=None,
    is_default=False,
):
    """Register a new vehicle under the authenticated customer."""
    if not registration_no or not registration_no.strip():
        return None, "Vehicle registration number is required."

    reg = registration_no.strip().upper()
    existing = query_one("SELECT vehicle_id FROM Vehicles WHERE registration_no = %s", (reg,))
    if existing:
        return None, f"Vehicle registration number '{reg}' is already registered."

    try:
        capacity = float(battery_capacity_kwh)
        if capacity <= 0:
            return None, "Battery capacity must be greater than 0 kWh."
    except (ValueError, TypeError):
        return None, "Battery capacity must be a positive number."

    category = (vehicle_category or "4W_SUV").strip().upper()
    if category not in VALID_VEHICLE_CATEGORIES:
        category = "4W_SUV"

    connector = (connector_type or "CCS2").strip().upper()
    if connector not in VALID_CONNECTOR_TYPES:
        connector = "CCS2"

    year = None
    if registration_year:
        try:
            year = int(registration_year)
            if year < 1990 or year > 2035:
                year = None
        except (ValueError, TypeError):
            year = None

    # Check if this will be the customer's first vehicle
    count_row = query_one("SELECT COUNT(*) AS cnt FROM Vehicles WHERE user_id = %s", (user_id,))
    first_vehicle = bool(count_row and count_row["cnt"] == 0)
    default_flag = 1 if (is_default or first_vehicle) else 0

    with transaction() as cur:
        if default_flag:
            cur.execute("UPDATE Vehicles SET is_default = 0 WHERE user_id = %s", (user_id,))

        cur.execute(
            "INSERT INTO Vehicles (user_id, registration_no, make, model, battery_capacity_kwh, "
            "                     vehicle_category, connector_type, registration_year, is_default) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, reg, make.strip(), model.strip(), capacity, category, connector, year, default_flag)
        )
        vid = cur.lastrowid
        return vid, None


def update_vehicle(
    vehicle_id,
    user_id,
    registration_no,
    make,
    model,
    battery_capacity_kwh,
    vehicle_category=None,
    connector_type=None,
    registration_year=None,
    is_default=None,
):
    """Update vehicle details, ensuring ownership and unique registration number."""
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    if not vehicle:
        return False, "Vehicle not found or you do not have permission to edit it."

    reg = registration_no.strip().upper()
    existing = query_one(
        "SELECT vehicle_id FROM Vehicles WHERE registration_no = %s AND vehicle_id != %s",
        (reg, vehicle_id)
    )
    if existing:
        return False, f"Registration number '{reg}' is already taken by another vehicle."

    try:
        capacity = float(battery_capacity_kwh)
        if capacity <= 0:
            return False, "Battery capacity must be greater than 0 kWh."
    except (ValueError, TypeError):
        return False, "Invalid battery capacity value."

    category = (vehicle_category or vehicle.get("vehicle_category") or "4W_SUV").strip().upper()
    if category not in VALID_VEHICLE_CATEGORIES:
        category = vehicle.get("vehicle_category") or "4W_SUV"

    connector = (connector_type or vehicle.get("connector_type") or "CCS2").strip().upper()
    if connector not in VALID_CONNECTOR_TYPES:
        connector = vehicle.get("connector_type") or "CCS2"

    year = vehicle.get("registration_year")
    if registration_year is not None:
        try:
            year = int(registration_year) if str(registration_year).strip() else None
        except (ValueError, TypeError):
            year = None

    default_flag = int(vehicle.get("is_default", 0))
    if is_default is not None:
        default_flag = 1 if is_default else 0

    with transaction() as cur:
        if default_flag:
            cur.execute("UPDATE Vehicles SET is_default = 0 WHERE user_id = %s", (user_id,))

        cur.execute(
            "UPDATE Vehicles SET registration_no = %s, make = %s, model = %s, battery_capacity_kwh = %s, "
            "                    vehicle_category = %s, connector_type = %s, registration_year = %s, is_default = %s "
            "WHERE vehicle_id = %s AND user_id = %s",
            (reg, make.strip(), model.strip(), capacity, category, connector, year, default_flag, vehicle_id, user_id)
        )
    return True, None


def set_default_vehicle(user_id, vehicle_id):
    """Set a specific vehicle as the primary/default vehicle for the customer."""
    veh = get_vehicle_by_id(vehicle_id, user_id)
    if not veh:
        return False, "Vehicle not found."

    with transaction() as cur:
        cur.execute("UPDATE Vehicles SET is_default = 0 WHERE user_id = %s", (user_id,))
        cur.execute("UPDATE Vehicles SET is_default = 1 WHERE vehicle_id = %s AND user_id = %s", (vehicle_id, user_id))
    return True, None


def delete_vehicle(vehicle_id, user_id):
    """Delete a vehicle owned by the authenticated customer."""
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    if not vehicle:
        return False, "Vehicle not found or you do not have permission to delete it."

    active = query_one(
        "SELECT booking_id FROM Bookings "
        "WHERE vehicle_id = %s AND booking_status IN ('PENDING', 'CONFIRMED')",
        (vehicle_id,)
    )
    if active:
        return False, "Cannot delete vehicle with active or upcoming bookings."

    with transaction() as cur:
        cur.execute("DELETE FROM Vehicles WHERE vehicle_id = %s AND user_id = %s", (vehicle_id, user_id))
        if vehicle.get("is_default"):
            # Assign is_default to the next remaining vehicle if any
            cur.execute(
                "UPDATE Vehicles SET is_default = 1 WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                (user_id,)
            )
    return True, None

