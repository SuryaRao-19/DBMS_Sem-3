"""
Charging Session & Payment Settlement Tests
EV Charging Station Management System - DBMS Capstone Project
"""
import pytest
from app.services.session_service import start_session, complete_session, get_session_by_id
from app.services.payment_service import record_payment
from app.db import execute, query_one


def test_charging_session_lifecycle_and_stored_procedure():
    """
    Test complete charging lifecycle:
    1. Start session -> Point becomes OCCUPIED
    2. Complete session via MySQL Stored Procedure CompleteChargingSession ->
       Cost computed via CalculateChargingCost, point restored to AVAILABLE
    3. Settle payment -> Payment record added to ledger with unique reference
    """
    user_id = 2
    vehicle_id = 1
    point_id = 1

    # Ensure point is AVAILABLE
    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = %s", (point_id,))
    # Ensure no lingering active session
    execute("DELETE FROM ChargingSessions WHERE user_id = %s AND session_status = 'IN_PROGRESS'", (user_id,))

    # 1. Start Session
    session_id, err = start_session(user_id=user_id, vehicle_id=vehicle_id, point_id=point_id)
    assert err is None
    assert session_id is not None

    point_after_start = query_one("SELECT point_status, tariff_per_kwh FROM ChargingPoints WHERE point_id = %s", (point_id,))
    assert point_after_start["point_status"] == "OCCUPIED"
    tariff = float(point_after_start["tariff_per_kwh"])

    # 2. Complete Session with 25.0 kWh delivered
    energy_kwh = 25.000
    expected_cost = round(energy_kwh * tariff, 2)

    completed, err2 = complete_session(session_id=session_id, energy_kwh=energy_kwh, user_id=user_id)
    assert err2 is None
    assert completed is not None
    assert completed["session_status"] == "COMPLETED"
    assert float(completed["energy_kwh"]) == 25.000
    assert float(completed["total_cost"]) == expected_cost

    point_after_complete = query_one("SELECT point_status FROM ChargingPoints WHERE point_id = %s", (point_id,))
    assert point_after_complete["point_status"] == "AVAILABLE"

    # 3. Record Payment
    payment_id, pay_err = record_payment(session_id=session_id, payment_method="UPI", payment_status="SUCCESS")
    assert pay_err is None
    assert payment_id is not None

    payment = query_one("SELECT * FROM Payments WHERE payment_id = %s", (payment_id,))
    assert float(payment["amount"]) == expected_cost
    assert payment["payment_status"] == "SUCCESS"
    assert payment["transaction_reference"].startswith("EVTXN-")

    # Cleanup test records
    execute("DELETE FROM Payments WHERE payment_id = %s", (payment_id,))
    execute("DELETE FROM ChargingSessions WHERE session_id = %s", (session_id,))


def test_reject_negative_energy_completion():
    """Verify that completing a session with negative energy is rejected."""
    user_id = 2
    vehicle_id = 1
    point_id = 1

    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = %s", (point_id,))
    execute("DELETE FROM ChargingSessions WHERE user_id = %s AND session_status = 'IN_PROGRESS'", (user_id,))

    session_id, _ = start_session(user_id=user_id, vehicle_id=vehicle_id, point_id=point_id)
    assert session_id is not None

    completed, err = complete_session(session_id=session_id, energy_kwh=-10.500, user_id=user_id)
    assert completed is None
    assert "Energy consumed cannot be negative" in err

    # Cleanup
    execute("DELETE FROM ChargingSessions WHERE session_id = %s", (session_id,))
    execute("UPDATE ChargingPoints SET point_status = 'AVAILABLE' WHERE point_id = %s", (point_id,))


def test_reject_duplicate_payment_transaction_reference():
    """Verify that duplicate transaction references are rejected by UNIQUE constraint."""
    # Use session 1 (seeded)
    duplicate_ref = "EVTXN-TEST-DUP-REF-001"
    execute("DELETE FROM Payments WHERE transaction_reference = %s", (duplicate_ref,))

    # Insert first payment
    execute(
        "INSERT INTO Payments (session_id, transaction_reference, amount, payment_method, payment_status, paid_at) "
        "VALUES (1, %s, 100.00, 'UPI', 'SUCCESS', NOW())",
        (duplicate_ref,)
    )

    # Attempt to insert second payment with same transaction reference
    duplicate_error = False
    try:
        execute(
            "INSERT INTO Payments (session_id, transaction_reference, amount, payment_method, payment_status, paid_at) "
            "VALUES (2, %s, 200.00, 'CARD', 'SUCCESS', NOW())",
            (duplicate_ref,)
        )
    except Exception as e:
        duplicate_error = True
        assert "Duplicate entry" in str(e) and "transaction_reference" in str(e)

    assert duplicate_error is True

    # Cleanup
    execute("DELETE FROM Payments WHERE transaction_reference = %s", (duplicate_ref,))
