# Dual QR Code Architecture & Security Workflow

The portal strictly separates **Station Identification QRs** (static physical asset signage) from **Dynamic Payment QRs** (short-lived single-use billing payloads).

---

## A. Station Identification QR (`StationQRCodes`)

- **Purpose**: Physical charger pedestal / signage placard pointing drivers to a station's verified public page. Contains zero user PII and zero payment state.
- **Database Table**: `StationQRCodes (qr_id, station_id, qr_token, qr_status, expires_at, scan_count, last_scanned_at, created_by, created_at, revoked_at)`.
- **Public Scan Flow**:
  1. Driver scans printed placard encoding `/qr/station/<opaque_token>`.
  2. `record_qr_scan_by_token()` verifies token existence and checks `qr_status == 'ACTIVE'` and non-expiration.
     - Unknown token -> HTTP `404` (`qr_status.html`).
     - Revoked/Expired token -> HTTP `410 Gone` (`qr_status.html`).
  3. Valid scan atomically increments `scan_count`, updates `last_scanned_at`, and redirects (`302`) to canonical `/station/<station_slug>?qr=verified`.
  4. Image preview `/qr/station/<token>/image.png` renders crisp local PNG output without incrementing scan telemetry.
- **Admin Governance (`/admin/stations`)**:
  - **Download PNG / SVG**: `/admin/stations/<id>/qr/png`, `/admin/stations/<id>/qr/svg`.
  - **Print Signage Placard**: `/admin/stations/<id>/qr/print`.
  - **Regenerate Token**: `POST /admin/stations/<id>/qr/regenerate` marks previous tokens `REVOKED` and issues a fresh opaque `secrets.token_urlsafe` token + audit log.
  - **Revoke Token**: `POST /admin/stations/<id>/qr/revoke` deactivates active token + audit log.

---

## B. Dynamic Payment QR (`Payments` + `razorpay_service.py`)

- **Purpose**: Single-use, server-priced checkout QR generated on `/owner/checkout/<session_id>`.
- **Generation (`POST /api/payments/razorpay/qr`)**:
  - Creates/reuses a server-priced `PENDING` Razorpay test order (`order_sim_*` or Razorpay QR API `qr_*`), stores `payment_qr_id`, `payment_qr_payload`, and `qr_expires_at = NOW() + 10 minutes`.
  - Returns an inline base64 PNG (`data:image/png;base64,...`) rendered strictly by Python `qrcode`.
- **Non-Settlement Rule & Expiry**:
  - Opening or scanning the Dynamic Payment QR **never** marks a payment `SUCCESS`.
  - Settlement happens only via HMAC-SHA256 verification (`/verify` / `/sandbox-complete`) or signed webhook (`/webhook`).
  - Once `qr_expires_at` passes, settlement attempts fail cleanly (`400`) and mark the pending QR row `EXPIRED`, requiring the user to regenerate a fresh QR.

