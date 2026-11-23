# Web3Forms Contact & Enquiry Setup Guide

## Architecture Overview
User enquiries on `/contact` are submitted to a **Flask backend proxy** (`POST /contact` -> `app/services/contact_service.py`), **never** directly from browser JavaScript:

1. **CSRF & Validation**: Flask-WTF validates the CSRF token, followed by server-side field length, email syntax, category whitelist, CR/LF/NUL email header sanitization, and honeypot (`botcheck`) checks.
2. **DB-Backed Anti-Spam & Duplicate Lock**: Before accepting, MySQL `ContactMessages` checks for identical submissions within 5 minutes and caps submissions at 5 per 10 minutes per email/IP (compatible with stateless Vercel instances).
3. **Resilient Dual Storage**:
   - The validated enquiry is immediately saved to MySQL `ContactMessages` (`submission_status='NEW'`, `email_delivery_status='PENDING'`).
   - Flask calls `https://api.web3forms.com/submit` with `WEB3FORMS_ACCESS_KEY`.
   - On HTTP 200 + `{"success": true}`, `email_delivery_status` updates to `'SENT'` and the user sees a confirmation flash.
   - If `WEB3FORMS_ACCESS_KEY` is missing or the API fails/times out, the database row is **preserved** with `email_delivery_status='FAILED'` and the user is shown a warning (`HTTP 502`) without a false success message.
4. **Admin Portal**: Admins review submissions, inspect email delivery status, and advance workflow state (`NEW` -> `IN_PROGRESS` -> `RESOLVED`) at `/admin/enquiries` (logged in `AuditLogs`).

---

## Step-by-Step Configuration

1. Visit **https://web3forms.com/** and enter your destination support email address to receive your free **Access Key**.
2. Add the key to your local `.env` (for testing) and your Vercel **Environment Variables** (for production):
   ```env
   WEB3FORMS_ACCESS_KEY=your-real-uuid-access-key-here
   ```
3. Never commit `.env` or paste your key into client-side templates/JavaScript.

---

## Live Verification Status
- **Backend validation, DB persistence, failure fallback (`FAILED` status preservation), duplicate/rate limits, CSRF, and Admin UI**: Automated tests verified (`tests/test_contact_web3forms.py`, mocked Web3Forms HTTP client).
- **Live Email Delivery to Inbox**: Requires setting a real `WEB3FORMS_ACCESS_KEY` and submitting a test enquiry on `/contact`, then confirming receipt in your inbox and `email_delivery_status = 'SENT'` under `/admin/enquiries`.

