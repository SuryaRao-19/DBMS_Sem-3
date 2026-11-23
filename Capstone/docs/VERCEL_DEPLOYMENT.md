# Vercel Serverless Deployment Guide

## How This Flask App Runs on Vercel

Vercel hosts Python WSGI apps as **stateless serverless functions** rather than persistent background processes:

- **`api/index.py`**: Exports `app = create_app()` for Vercel's `@vercel/python` runtime.
- **`vercel.json`**: Uses modern `functions` (`maxDuration: 30`) and `rewrites` routing all requests through `/api/index` without deprecated `builds` keys.
- **`requirements.txt`**: Lists all production Python packages at the repository root so Vercel installs them automatically (`Flask`, `Flask-WTF`, `pymysql`, `DBUtils`, `cryptography`, `python-dotenv`, `Werkzeug`, `requests`).
- **`.vercelignore`**: Excludes `tests/`, `docs/`, `scratch/`, `screenshots/`, `.env`, local archives, and caches to keep the serverless bundle lean.
- **Stateless Requests**: Sessions are stored in signed HTTP-only cookies (using `SECRET_KEY`), rate-limiting and audit trails live in MySQL, and `DBUtils.PooledDB` maintains conservative per-worker connection limits.

---

## End-to-End Deployment Flow: Local -> GitHub -> Managed MySQL -> Vercel

### Step 1: Provision Managed MySQL 8.0+
Follow [`docs/DATABASE_SETUP.md`](./DATABASE_SETUP.md) to create a MySQL 8.0 database (e.g., on **Aiven**, **DigitalOcean**, or **AWS RDS**) and run:
```bash
python init_db.py --mode full
```
Copy your connection URI (`mysql://user:pass@host:port/ev_charging_db?ssl_mode=REQUIRED`) and SSL CA certificate if required.

### Step 2: Push Project to GitHub
```bash
git init
git add .
# Verify .env is NOT staged! (.gitignore excludes .env and *.env while keeping .env.example)
git status
git commit -m "Prepare EV ChargeNet for production deployment"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

### Step 3: Import into Vercel
1. Log in to **https://vercel.com** and click **Add New... -> Project**.
2. Import your GitHub repository. Keep Framework Preset as **Other** (`vercel.json` handles routing).
3. Before clicking **Deploy**, expand **Environment Variables** and add:

| Variable | Required | Value Example |
| :--- | :--- | :--- |
| `FLASK_ENV` | Yes | `production` |
| `SECRET_KEY` | Yes | Output of `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Yes | `mysql://user:pass@host:port/ev_charging_db?ssl_mode=REQUIRED` |
| `MYSQL_SSL_CA` | If provider requires custom CA | Paste PEM contents of your provider CA cert (or path) |
| `WEB3FORMS_ACCESS_KEY` | Yes (for Contact email delivery) | Your Web3Forms UUID access key (processed server-side by Flask only) |
| `RAZORPAY_KEY_ID` | Optional (TEST MODE ONLY) | `rzp_test_...` test key ID (`rzp_live_*` is blocked; falls back to signed local sandbox when empty) |
| `RAZORPAY_KEY_SECRET` | Optional (TEST MODE ONLY) | Razorpay Test Mode secret (server-side HMAC-SHA256 verification only) |
| `RAZORPAY_WEBHOOK_SECRET` | Optional (for webhooks) | Webhook signing secret verified against `X-Razorpay-Signature` |
| `SUPABASE_URL` | Optional (inactive under MySQL) | Optional Supabase project URL (never used for MySQL DB auth) |
| `SUPABASE_PUBLISHABLE_KEY` | Optional (inactive under MySQL) | Public client key only; never replaces Flask RBAC/IDOR checks |
| `GOOGLE_MAPS_API_KEY` | Optional | Google Maps JS API key (restricted by HTTP referrer; falls back to Leaflet/OpenStreetMap when omitted) |
| `GOOGLE_CLIENT_ID` | Optional (for Google Login) | Google Cloud OAuth 2.0 Web Client ID |
| `GOOGLE_CLIENT_SECRET` | Optional (for Google Login) | Google Cloud OAuth 2.0 Client Secret (server-side only; never exposed to client JS) |
| `GOOGLE_REDIRECT_URI` | Optional (for Google Login) | `https://<your-app>.vercel.app/auth/google/callback` (defaults to dynamic HTTPS callback URI when omitted) |
| `OPEN_CHARGE_MAP_API_KEY` | Optional (for OCM POI Sync) | Free Open Charge Map API v3 key (`X-API-Key` header; sync safely reports unconfigured when blank) |
| `NOMINATIM_USER_AGENT` | Optional (has default) | `EZChargeNetworkPortal/1.0 (contact@example.com)` per OpenStreetMap Nominatim policy |
| `MYSQL_POOL_MAX_CONNECTIONS` | Optional | `5` (recommended for serverless) |

> **Razorpay Webhook URL (if configuring Razorpay Dashboard Test Mode):** Point webhooks to `https://<your-app>.vercel.app/api/payments/razorpay/webhook` for `payment.captured`, `payment.failed`, and `order.paid`, and copy the signing secret into `RAZORPAY_WEBHOOK_SECRET`. Never configure `rzp_live_*` keys on this academic demonstration deployment.

4. Click **Deploy**.

### Step 4: Post-Deploy Smoke Checks
1. Visit `https://<your-app>.vercel.app/api/health` -> verify `{"status": "HEALTHY", "database_connected": true}`.
2. Visit `/api/stations/map` -> verify 14 approved Delhi NCR hubs with coordinates return `200 OK`.
3. Visit `/stations`, `/about`, `/data-sources`, and `/contact` -> confirm interactive map pins load, CSS/JS assets resolve cleanly, and test contact enquiry submission (verify `email_delivery_status = 'SENT'` and inbox receipt).
4. Log in with your seeded/provisioned Admin credentials, visit `/admin/system-health`, `/admin/data-sources`, and `/admin/enquiries`, and confirm `SESSION_COOKIE_SECURE` (`Secure` flag) is active over HTTPS.

---

## Troubleshooting Vercel Deployments
- **500 on startup (`RuntimeError: SECRET_KEY environment variable is required`)**: Ensure `SECRET_KEY` is added to Vercel Project Settings -> Environment Variables for the target environment (Production/Preview) and redeploy.
- **Database timeout or SSL error**: Verify your Managed MySQL firewall/IP allowlist permits connections from Vercel (`0.0.0.0/0` with TLS/SSL required + strong password, or provider VPC integration) and `ssl_mode=REQUIRED` is included in `DATABASE_URL`.
- **`CompleteChargingSession` fails**: Confirm stored routines (`03_routines_triggers.sql`) were applied on the cloud DB (`python init_db.py --mode full`). Note AWS RDS requires parameter `log_bin_trust_function_creators=1`.

