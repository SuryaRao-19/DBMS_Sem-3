# Razorpay TEST MODE & Dynamic Payment QR Setup

> **Strict Academic Safeguard:** Live merchant keys (`rzp_live_*`) are explicitly rejected in `app/services/razorpay_service.py`. Only **Razorpay Test Mode (`rzp_test_*`)** or deterministic local HMAC-SHA256 sandbox simulation is permitted.

---

## 1. Environment Variables

Configure these keys in `.env` (or Vercel Project Settings):

```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_test_key_secret
RAZORPAY_WEBHOOK_SECRET=your_test_webhook_secret
```

When `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are omitted locally, `razorpay_service.py` automatically falls back to deterministic local **Test Sandbox Mode** (`order_sim_*`, `pay_sim_*`, `qr_sim_*`) using cryptographically verified HMAC-SHA256 signatures so automated tests and offline demos run identically without internet calls.

---

## 2. Payment Lifecycle & Security Controls

1. **Server-Computed Order (`POST /api/payments/razorpay/order`)**:
   - Verifies session ownership (`ChargingSessions.user_id == session["user_id"]`).
   - Recomputes total INR & paise amount strictly from server `ChargingSessions.total_cost` (with 18% included GST breakdown). Client-submitted amounts are ignored.
2. **Dynamic Payment QR (`POST /api/payments/razorpay/qr`)**:
   - Generates a single-use fixed-amount UPI/Razorpay test QR bound to the session order with a **10-minute expiration (`qr_expires_at`)**.
   - **Scanning alone does NOT complete payment.** Checkout UI enforces a live countdown timer transitions cleanly to `EXPIRED` + `Retry & Regenerate QR` when expired, and settlement attempts against expired QRs are rejected in MySQL with `payment_status = 'EXPIRED'`.
3. **HMAC-SHA256 Verification (`POST /api/payments/razorpay/verify`, `/sandbox-complete`)**:
   - Verifies `HMAC_SHA256(razorpay_order_id + "|" + razorpay_payment_id, secret)` via constant-time `hmac.compare_digest` before transitioning `Payments` to `SUCCESS` / `CAPTURED`.
4. **Idempotent Webhooks (`POST /api/payments/razorpay/webhook`)**:
   - Verifies `X-Razorpay-Signature` HMAC-SHA256 over the raw request body.
   - Records `event_id` in `PaymentWebhookEvents` to guarantee idempotency across retries and refuses out-of-order downgrades on already settled payments (`payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`, `refund.processed`).

