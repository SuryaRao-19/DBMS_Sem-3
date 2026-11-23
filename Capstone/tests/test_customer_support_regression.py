"""
Phase 1 & Phase 11 Regression Tests: Customer Support Desk
Verifies data contract normalization, empty states, existing tickets,
category mapping, ticket creation, and error resilience.
"""
from app.db import execute, query_one, query_all
from app.services.contact_service import get_support_categories, SUPPORT_CATEGORIES_DICT


def test_support_categories_dict_contract():
    """Verify get_support_categories returns a dictionary contract with .items()."""
    cats = get_support_categories()
    assert isinstance(cats, dict)
    assert len(cats) >= 6
    assert "GENERAL" in cats
    assert "BOOKING" in cats
    assert "PAYMENT" in cats
    # Verify .items() does not raise
    items = list(cats.items())
    assert len(items) == len(cats)


def test_customer_support_page_loads_and_handles_empty_tickets(app):
    """Verify /customer/support loads cleanly for an authenticated customer with no tickets."""
    test_email = "ishita@example.com"
    execute("DELETE FROM ContactMessages WHERE email = %s", (test_email,))

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 7
        sess["full_name"] = "Ishita Rao"
        sess["email"] = test_email
        sess["role"] = "CUSTOMER"

    res = client.get("/customer/support")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Customer Help &amp; Support Desk" in html or "Customer Help & Support Desk" in html
    assert "Submit Support Ticket" in html
    assert "No support tickets submitted yet" in html


def test_customer_support_renders_existing_tickets_and_admin_response(app):
    """Verify /customer/support renders existing tickets, status badges, and admin responses."""
    test_email = "ishita@example.com"
    execute("DELETE FROM ContactMessages WHERE email = %s", (test_email,))
    cid = execute(
        "INSERT INTO ContactMessages "
        "(ticket_reference, full_name, email, subject, category, message, submission_status, admin_response, ip_address) "
        "VALUES ('TKT-99991', 'Ishita Rao', %s, 'Charger offline at CP-01', 'Charging station support', "
        "        'Dispenser was unresponsive.', 'IN_PROGRESS', 'We have dispatched a technician.', '127.0.0.1')",
        (test_email,)
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 7
        sess["full_name"] = "Ishita Rao"
        sess["email"] = test_email
        sess["role"] = "CUSTOMER"

    res = client.get("/customer/support")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "TKT-99991" in html
    assert "Charger offline at CP-01" in html
    assert "IN_PROGRESS" in html
    assert "Staff Response:" in html
    assert "We have dispatched a technician." in html

    # Clean up
    execute("DELETE FROM ContactMessages WHERE id = %s", (cid,))


def test_customer_support_submission_creates_ticket_and_reference(app):
    """Verify submitting the support form creates a persistent ticket with TKT- reference."""
    test_email = "ishita@example.com"
    execute("DELETE FROM ContactMessages WHERE email = %s", (test_email,))

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 7
        sess["full_name"] = "Ishita Rao"
        sess["email"] = test_email
        sess["role"] = "CUSTOMER"

    res = client.post(
        "/customer/support",
        data={
            "category": "BOOKING",
            "subject": "Unable to cancel pending booking unique",
            "message": "Encountered a gateway error while trying to cancel booking #101.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "TKT-" in html or "created successfully" in html

    saved = query_one("SELECT * FROM ContactMessages WHERE email = %s ORDER BY id DESC LIMIT 1", (test_email,))
    assert saved is not None
    assert saved["ticket_reference"] is not None
    assert saved["ticket_reference"].startswith("TKT-")
    assert "Unable to cancel" in saved["subject"]

    # Clean up
    execute("DELETE FROM ContactMessages WHERE id = %s", (saved["id"],))
