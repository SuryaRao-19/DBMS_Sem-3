"""
Payment and Financial Settlement Service (Demo Mode Only)
EV Charging Station Management System - Production Hardened
"""
import uuid
from datetime import datetime
from app.db import query_all, query_one, transaction

VALID_PAYMENT_METHODS = (
    "UPI",
    "CARD",
    "CREDIT_CARD",
    "DEBIT_CARD",
    "NET_BANKING",
    "WALLET",
    "CASH",
)
VALID_PAYMENT_STATUSES = ("PENDING", "SUCCESS", "FAILED", "REFUNDED")


def generate_transaction_ref():
    """Generate a unique simulated transaction reference."""
    return f"EVTXN-{uuid.uuid4().hex[:8].upper()}"


def record_payment(
    session_id,
    payment_method="UPI",
    payment_status="SUCCESS",
    transaction_reference=None,
    user_id=None,
    booking_id=None,
    simulation_note=None,
):
    """
    Record a DEMO payment ledger entry linked to a completed charging session.
    IMPORTANT: Strictly for academic demonstration. No real money is deducted and
    no real card or UPI credentials are stored.
    Enforces session ownership (when user_id is provided), server-side amount integrity,
    and transaction-locked prevention of duplicate SUCCESS settlements.
    """
    if not session_id:
        return None, "Charging session ID is required."

    method = (payment_method or "UPI").strip().upper().replace(" ", "_")
    if method not in VALID_PAYMENT_METHODS:
        return None, f"Unsupported demo payment method '{method}'."

    status = (payment_status or "SUCCESS").strip().upper()
    if status not in VALID_PAYMENT_STATUSES:
        return None, f"Invalid demo payment status '{status}'."

    tx_ref = transaction_reference or generate_transaction_ref()
    paid_at = datetime.now() if status == "SUCCESS" else None
    note = simulation_note or f"DEMO PAYMENT ({status}) — NO REAL MONEY CHARGED"

    try:
        with transaction() as cur:
            cur.execute(
                "SELECT session_id, booking_id, user_id, total_cost, session_status "
                "FROM ChargingSessions WHERE session_id = %s FOR UPDATE",
                (session_id,)
            )
            sess = cur.fetchone()
            if not sess:
                return None, "Charging session not found."

            if user_id is not None and int(sess["user_id"]) != int(user_id):
                return None, "Permission denied: Session does not belong to your account."

            if sess["session_status"] != "COMPLETED":
                return None, "Only completed charging sessions can be settled."

            amount = sess["total_cost"]
            if amount is None or amount < 0:
                return None, "Invalid billing amount."

            linked_booking_id = booking_id if booking_id is not None else sess.get("booking_id")

            cur.execute(
                "SELECT payment_id, transaction_reference FROM Payments "
                "WHERE session_id = %s AND payment_status = 'SUCCESS' FOR UPDATE",
                (session_id,)
            )
            existing = cur.fetchone()
            if existing:
                return None, f"Session is already settled under transaction {existing['transaction_reference']}."

            cur.execute(
                "INSERT INTO Payments "
                "(session_id, booking_id, transaction_reference, amount, payment_method, payment_status, paid_at, is_simulated, simulation_note) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)",
                (session_id, linked_booking_id, tx_ref, amount, method, status, paid_at, note[:250])
            )
            return cur.lastrowid, None
    except Exception as e:
        if "Duplicate entry" in str(e) and "transaction_reference" in str(e):
            return None, f"Duplicate transaction reference '{tx_ref}'. Payment rejected."
        return None, f"Payment recording failed: {str(e)}"


def get_payment_by_session(session_id, user_id=None):
    """Retrieve latest payment record for a given session, optionally scoped by user_id."""
    if user_id is not None:
        return query_one(
            "SELECT p.* FROM Payments p "
            "JOIN ChargingSessions cs ON cs.session_id = p.session_id "
            "WHERE p.session_id = %s AND cs.user_id = %s "
            "ORDER BY (p.payment_status = 'SUCCESS') DESC, p.created_at DESC LIMIT 1",
            (session_id, user_id)
        )
    return query_one(
        "SELECT payment_id, session_id, booking_id, transaction_reference, amount, "
        "       payment_method, payment_status, paid_at, is_simulated, simulation_note, created_at "
        "FROM Payments WHERE session_id = %s "
        "ORDER BY (payment_status = 'SUCCESS') DESC, created_at DESC LIMIT 1",
        (session_id,)
    )


def get_all_payments():
    """Admin view: Retrieve all simulated financial ledger records."""
    return query_all(
        "SELECT p.payment_id, p.session_id, p.booking_id, p.transaction_reference, p.amount, "
        "       p.payment_method, p.payment_status, p.paid_at, p.is_simulated, p.simulation_note, p.created_at, "
        "       p.gateway_provider, p.razorpay_order_id, p.razorpay_payment_id, "
        "       cs.user_id, cs.energy_kwh, cs.tariff_per_kwh, "
        "       u.full_name AS user_name, u.email AS user_email, "
        "       s.station_name, cp.point_code "
        "FROM Payments p "
        "JOIN ChargingSessions cs ON cs.session_id = p.session_id "
        "JOIN Users u ON u.user_id = cs.user_id "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "ORDER BY p.created_at DESC"
    )
