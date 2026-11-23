# Managed MySQL Database Setup & Migration Guide

## 1. Environment Configuration Options

`app/db.py` supports two configuration modes without source code changes:

### Option A: Single Connection URI (Recommended for Vercel / Cloud)
```env
DATABASE_URL=mysql://avnadmin:YOUR_PASSWORD@your-mysql-host.aivencloud.com:12345/ev_charging_db?ssl_mode=REQUIRED
MYSQL_SSL_CA=/path/to/ca.pem   # Optional if your CA bundle is custom; also supports PEM content directly in env var
```
URL-encoded special characters in passwords are automatically decoded via `urllib.parse.unquote`.

### Option B: Discrete Variables (Local Dev / Traditional Hosting)
```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ev_charging_db
MYSQL_SSL_REQUIRED=false
```

---

## 2. Serverless Connection Pooling & Query Architecture

- **Pooling (`DBUtils.PooledDB`)**: Configures persistent per-worker pools with `ping=1` health checks and conservative limits (`MYSQL_POOL_MIN_CACHED=0`, `MYSQL_POOL_MAX_CONNECTIONS=5` by default when `VERCEL` is set, configurable via env vars) to prevent `Too many connections` errors on cloud MySQL tiers.
- **Portable Metadata Queries**: `get_system_health()` uses `DATABASE()` instead of hardcoded schema names and performs case-insensitive table matching (`lower_case_table_names` safe across Windows and Linux).
- **Zero-N+1 Station Directory**: `get_all_stations()` aggregates `total_points` and `available_points` via a single `LEFT JOIN ChargingPoints` + `GROUP BY`.

---

## 3. Recommended Managed MySQL 8.0+ Providers for Vercel

Vercel runs stateless serverless functions and does not host persistent MySQL instances. Recommended cloud MySQL providers:

| Provider | Compatibility Notes | TLS / SSL |
| :--- | :--- | :--- |
| **Aiven for MySQL** (Recommended free/starter tier) | Full MySQL 8.0 with stored procedures (`CompleteChargingSession`), deterministic functions (`CalculateChargingCost`), and triggers (`trg_booking_before_insert`, `trg_session_before_insert`). | Requires SSL (`?ssl_mode=REQUIRED` + downloadable `ca.pem`). |
| **DigitalOcean Managed MySQL** | Native MySQL 8.0, automated daily backups, predictable pricing. | Requires SSL + CA certificate. |
| **Railway / AWS RDS for MySQL** | Standard InnoDB MySQL 8.0. Note on AWS RDS: ensure `log_bin_trust_function_creators=1` in the DB Parameter Group before creating stored functions/triggers. | Supported (`ssl_mode=REQUIRED`). |

> **Note on PlanetScale / Vitess**: Avoid PlanetScale if you rely on foreign keys and triggers without adjustment, as Vitess disables standard MySQL stored triggers/FK enforcement in some modes. Choose a standard MySQL 8.0 engine (`InnoDB`) like Aiven, DigitalOcean, or AWS RDS.

---

## 4. Initializing & Migrating Without Data Loss

`init_db.py` executes pure Python SQL parsing via `PyMySQL` (supporting `DELIMITER $$` triggers/procedures cleanly on Linux, macOS, and Windows without needing `mysql.exe`).

### Non-Destructive Schema Migration (Preserves Existing Data)
```bash
# Applies ordered migrations in database/migrations/ safely using IF NOT EXISTS
python init_db.py --mode migrate
```

### Fresh Cloud Database Provisioning (Schema + Routines + Optional Demo Seed)
```bash
# 1. Backup local database first (if migrating existing data)
mysqldump -u root -p --single-transaction --routines --triggers ev_charging_db > backup_local.sql

# 2. Point DATABASE_URL in .env to your managed MySQL 8.0 instance, then initialize:
python init_db.py --mode full

# Optional: include sample stations, chargers, and accounts for staging/demo:
python init_db.py --mode full --seed-demo
```

Or import a clean dump directly into Aiven/RDS:
```bash
mysql -h YOUR_HOST -P YOUR_PORT -u avnadmin -p --ssl-ca=ca.pem ev_charging_db < backup_local.sql
```
*(Verify no hardcoded definer blocks your import; `03_routines_triggers.sql` omits `DEFINER=` so `init_db.py --mode full` creates routines cleanly under any managed user.)*

