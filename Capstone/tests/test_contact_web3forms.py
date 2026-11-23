"""
Phase 4 Verification Tests — Web3Forms Contact Proxy & Admin Enquiry Management
Tests validation, CSRF protection, spam/rate-limiting, header sanitization,
Web3Forms delivery & failure resilience, and Admin authorization.
"""
import re
import uuid
from unittest.mock import Mock, patch
import requests
from app.db import query_one, execute


def _extract_csrf(html_bytes):
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_bytes.decode("utf-8", errors="ignore"))
    assert match, "CSRF token input not found in HTML response"
    return match.group(1)


def _cleanup_contact(contact_id=None, email=None):
    if contact_id:
        execute("DELETE FROM ContactMessages WHERE id = %s", (contact_id,))
    elif email:
        execute("DELETE FROM ContactMessages WHERE email = %s", (email,))


def test_contact_page_renders_and_exposes_no_secret_key(client, app):
    """GET /contact renders all required fields without leaking WEB3FORMS_ACCESS_KEY."""
    app.config["WEB3FORMS_ACCESS_KEY"] = "super_secret_w3f_test_key_12345"
    resp = client.get("/contact")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Full Name" in body
    assert "Email Address" in body
    assert "Enquiry Category" in body
    assert "General enquiry" in body
    assert "super_secret_w3f_test_key_12345" not in body


def test_contact_requires_valid_csrf_token(csrf_client):
    """POST /contact without CSRF token is rejected with 400."""
    resp = csrf_client.post("/contact", data={
        "full_name": "Test Driver",
        "email": "driver@example.com",
        "category": "General enquiry",
        "subject": "CSRF check",
        "message": "This submission should fail without a CSRF token.",
    })
    assert resp.status_code == 400


def test_contact_valid_submission_persists_and_sends_web3forms(csrf_client, csrf_app):
    """Valid /contact POST saves to MySQL and forwards sanitized payload to Web3Forms."""
    csrf_app.config["WEB3FORMS_ACCESS_KEY"] = "valid_mock_access_key"
    unique_email = f"contact_{uuid.uuid4().hex[:8]}@example.com"
    try:
        token = _extract_csrf(csrf_client.get("/contact").data)
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "message": "Email sent"}

        with patch("app.services.contact_service.requests.post", return_value=mock_resp) as mock_post:
            resp = csrf_client.post(
                "/contact",
                data={
                    "csrf_token": token,
                    "full_name": "Meera\r\nBcc:evil@attacker.test Nair",
                    "email": unique_email,
                    "phone": "+91 98000 12345",
                    "category": "Charging station support",
                    "subject": "Charger\nReply-To:spoof@evil.com connector",
                    "message": "Station charger #2 at Indiranagar appears offline.",
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"received and forwarded" in resp.data

        mock_post.assert_called_once()
        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload["access_key"] == "valid_mock_access_key"
        assert sent_payload["replyto"] == unique_email
        assert "\r" not in sent_payload["subject"] and "\n" not in sent_payload["subject"]
        assert "\r" not in sent_payload["name"] and "\n" not in sent_payload["name"]

        row = query_one("SELECT * FROM ContactMessages WHERE email = %s", (unique_email,))
        assert row is not None
        assert row["email_delivery_status"] == "SENT"
        assert row["submission_status"] == "NEW"
    finally:
        _cleanup_contact(email=unique_email)


def test_contact_preserves_db_record_when_web3forms_fails(client, app):
    """When Web3Forms returns an error or times out, DB row is preserved with FAILED status and no false success is shown."""
    app.config["WEB3FORMS_ACCESS_KEY"] = "valid_mock_access_key"
    unique_email = f"fail_{uuid.uuid4().hex[:8]}@example.com"
    try:
        with patch("app.services.contact_service.requests.post", side_effect=requests.Timeout("Timed out")):
            resp = client.post("/contact", data={
                "full_name": "Karan Rao",
                "email": unique_email,
                "category": "Booking issue",
                "subject": "Booking confirmation delayed",
                "message": "My reservation at MG Road Hub did not send an alert.",
            })

        assert resp.status_code == 502
        body = resp.data.decode("utf-8")
        assert "email delivery" in body.lower() or "saved in our system" in body.lower()
        assert "received and forwarded" not in body

        row = query_one("SELECT * FROM ContactMessages WHERE email = %s", (unique_email,))
        assert row is not None
        assert row["email_delivery_status"] == "FAILED"
        assert row["submission_status"] == "NEW"
    finally:
        _cleanup_contact(email=unique_email)


def test_contact_validation_honeypot_duplicate_and_rate_limit(client, app):
    """Verify server-side validation, honeypot blocking, duplicate prevention, and rate limiting."""
    app.config["WEB3FORMS_ACCESS_KEY"] = "valid_mock_access_key"
    unique_email = f"limit_{uuid.uuid4().hex[:8]}@example.com"
    try:
        # 1. Invalid email
        bad_email = client.post("/contact", data={
            "full_name": "Tester",
            "email": "not-an-email",
            "category": "General enquiry",
            "subject": "Hello",
            "message": "Valid message length here.",
        })
        assert bad_email.status_code == 400

        # 2. Honeypot triggered
        spam = client.post("/contact", data={
            "full_name": "Bot User",
            "email": unique_email,
            "category": "General enquiry",
            "subject": "Buy cheap crypto",
            "message": "Spam message content that should be dropped.",
            "botcheck": "http://spam.example",
        })
        assert spam.status_code == 400
        assert query_one("SELECT id FROM ContactMessages WHERE email = %s", (unique_email,)) is None

        # 3. Duplicate submission prevention
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {"success": True}
        with patch("app.services.contact_service.requests.post", return_value=mock_resp):
            first = client.post("/contact", data={
                "full_name": "Repeat User",
                "email": unique_email,
                "category": "Payment issue",
                "subject": "Receipt question",
                "message": "Please verify receipt #101 payment amount.",
            }, follow_redirects=False)
            assert first.status_code == 302

            dup = client.post("/contact", data={
                "full_name": "Repeat User",
                "email": unique_email,
                "category": "Payment issue",
                "subject": "Receipt question",
                "message": "Please verify receipt #101 payment amount.",
            })
            assert dup.status_code == 400
            assert b"Duplicate enquiry detected" in dup.data

            # 4. Rate limit after 5 recent submissions from same email/IP
            for idx in range(2, 6):
                r = client.post("/contact", data={
                    "full_name": "Repeat User",
                    "email": unique_email,
                    "category": "Payment issue",
                    "subject": f"Receipt question #{idx}",
                    "message": f"Follow-up message number {idx} for billing.",
                })
                assert r.status_code == 302

            blocked = client.post("/contact", data={
                "full_name": "Repeat User",
                "email": unique_email,
                "category": "Payment issue",
                "subject": "Receipt question #6",
                "message": "Sixth message within 10 minutes should be rate-limited.",
            })
            assert blocked.status_code == 400
            assert b"Too many enquiries" in blocked.data
    finally:
        _cleanup_contact(email=unique_email)


def test_admin_enquiries_authorization_and_status_update(client, owner_client, admin_client):
    """Only ADMIN can view /admin/enquiries and update enquiry workflow status."""
    # Anonymous redirected
    anon = client.get("/admin/enquiries")
    assert anon.status_code == 302

    # Owner gets 403
    owner_resp = owner_client.get("/admin/enquiries")
    assert owner_resp.status_code == 403

    # Create a sample enquiry cleanly
    unique_email = f"admin_enq_{uuid.uuid4().hex[:8]}@example.com"
    msg_id = execute(
        "INSERT INTO ContactMessages (full_name, email, subject, category, message, submission_status, email_delivery_status) "
        "VALUES (%s, %s, %s, %s, %s, 'NEW', 'SENT')",
        ("Ananya Singh", unique_email, "Fleet enquiry", "Business partnership", "Looking to partner for 20 fleet EVs.")
    )
    try:
        # Owner cannot update status
        owner_post = owner_client.post(f"/admin/enquiries/{msg_id}/status", data={"submission_status": "RESOLVED"})
        assert owner_post.status_code == 403

        # Admin can list and update status
        list_resp = admin_client.get("/admin/enquiries")
        assert list_resp.status_code == 200
        assert b"Fleet enquiry" in list_resp.data

        upd_resp = admin_client.post(
            f"/admin/enquiries/{msg_id}/status",
            data={"submission_status": "RESOLVED"},
            follow_redirects=True,
        )
        assert upd_resp.status_code == 200
        row = query_one("SELECT submission_status FROM ContactMessages WHERE id = %s", (msg_id,))
        assert row["submission_status"] == "RESOLVED"
    finally:
        execute("DELETE FROM AuditLogs WHERE entity_name = 'ContactMessages' AND entity_id = %s", (msg_id,))
        _cleanup_contact(contact_id=msg_id)
