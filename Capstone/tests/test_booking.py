"""
Slot Booking & Conflict Validation Tests
EV Charging Station Management System - DBMS Capstone Project
"""
import pytest
from datetime import datetime, timedelta
from app.services.booking_service import create_booking, cancel_booking, get_user_bookings
from app.db import execute, query_one


def test_successful_booking_creation():
    """Verify that a valid booking is successfully recorded in database."""
    # Use User 2, Vehicle 1, Point 1 for future date
    start_dt = "2026-11-15 10:00:00"
    end_dt = "2026-11-15 11:00:00"

    # Cleanup any prior test record
    execute("DELETE FROM Bookings WHERE point_id = 1 AND start_at = %s", (start_dt,))

    booking_id, err = create_booking(user_id=2, vehicle_id=1, point_id=1, start_at=start_dt, end_at=end_dt)
    assert err is None
    assert booking_id is not None

    booking = query_one("SELECT * FROM Bookings WHERE booking_id = %s", (booking_id,))
    assert booking["booking_status"] == "CONFIRMED"
    assert booking["user_id"] == 2
    assert booking["point_id"] == 1

    # Cleanup
    execute("DELETE FROM Bookings WHERE booking_id = %s", (booking_id,))


def test_reject_overlapping_booking():
    """Verify that an overlapping slot reservation on the same charging point is rejected."""
    start_dt = "2026-11-20 14:00:00"
    end_dt = "2026-11-20 15:30:00"

    # 1. Create primary booking
    execute("DELETE FROM Bookings WHERE point_id = 1 AND start_at = %s", (start_dt,))
    b1, err1 = create_booking(user_id=2, vehicle_id=1, point_id=1, start_at=start_dt, end_at=end_dt)
    assert err1 is None
    assert b1 is not None

    # 2. Attempt overlapping booking (e.g. 14:30 to 15:00) by user 3, vehicle 2
    overlap_start = "2026-11-20 14:30:00"
    overlap_end = "2026-11-20 15:00:00"
    b2, err2 = create_booking(user_id=3, vehicle_id=2, point_id=1, start_at=overlap_start, end_at=overlap_end)

    assert b2 is None
    assert err2 is not None
    assert "already has a confirmed reservation" in err2 or "Overlapping booking" in err2

    # Cleanup
    execute("DELETE FROM Bookings WHERE booking_id = %s", (b1,))


def test_reject_invalid_date_range_end_before_start():
    """Verify that a booking where end_at precedes or equals start_at is rejected."""
    start_dt = "2026-11-25 15:00:00"
    end_dt = "2026-11-25 14:00:00"  # End is 1 hour before start

    b, err = create_booking(user_id=2, vehicle_id=1, point_id=1, start_at=start_dt, end_at=end_dt)
    assert b is None
    assert "Booking end time must be strictly after start time" in err or "Booking end must be after start" in err


def test_reject_booking_unowned_vehicle():
    """Verify that an EV owner cannot book using a vehicle registered to another user."""
    # Vehicle 2 belongs to User 3 (Priya Verma); User 2 (Aarav) attempts to book with it
    start_dt = "2026-11-28 10:00:00"
    end_dt = "2026-11-28 11:00:00"

    b, err = create_booking(user_id=2, vehicle_id=2, point_id=1, start_at=start_dt, end_at=end_dt)
    assert b is None
    assert "Selected vehicle does not belong to your account" in err or "Vehicle does not belong to this user" in err


def test_cancel_eligible_booking():
    """Verify that an authorized owner can cancel a confirmed booking."""
    start_dt = "2026-11-30 08:00:00"
    end_dt = "2026-11-30 09:00:00"

    booking_id, _ = create_booking(user_id=2, vehicle_id=1, point_id=1, start_at=start_dt, end_at=end_dt)
    assert booking_id is not None

    success, err = cancel_booking(booking_id, user_id=2)
    assert success is True
    assert err is None

    booking = query_one("SELECT booking_status FROM Bookings WHERE booking_id = %s", (booking_id,))
    assert booking["booking_status"] == "CANCELLED"

    # Cleanup
    execute("DELETE FROM Bookings WHERE booking_id = %s", (booking_id,))
