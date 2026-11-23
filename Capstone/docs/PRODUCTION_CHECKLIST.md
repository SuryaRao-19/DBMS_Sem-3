# Pre-Launch Production Checklist

Use this checklist before sharing the live URL publicly:

## Secrets & Security
- [ ] `FLASK_ENV=production` is set in Vercel Environment Variables.
- [ ] A cryptographically random `SECRET_KEY` (64+ hex chars) is configured in Vercel (never a dev fallback).
- [ ] `.env` is confirmed **not** tracked in Git (`git ls-files .env` returns empty).
- [ ] Default demo passwords (such as seeded capstone accounts) have been changed or deactivated in production via `/admin/users` or `/profile`.
- [ ] `WEB3FORMS_ACCESS_KEY` is set in environment variables (never embedded in HTML/JS).

## Database Integrity & Backups
- [ ] Managed MySQL 8.0+ instance uses TLS/SSL (`ssl_mode=REQUIRED`).
- [ ] All tables (`Users`, `Vehicles`, `Stations`, `ChargingPoints`, `Bookings`, `ChargingSessions`, `Payments`, `AuditLogs`, `SystemSettings`, `ContactMessages`), triggers, and stored routines (`CalculateChargingCost`, `CompleteChargingSession`) are installed via `python init_db.py --mode full` or verified migration.
- [ ] Automated daily backups are enabled on your Managed MySQL provider.
- [ ] `GET /api/health` returns `200 OK` with `"status": "HEALTHY"` and `"database_connected": true`.

## Functional Verification on Live URL
- [ ] Public `/`, `/stations`, and `/contact` load over HTTPS with clean styling and zero browser console errors.
- [ ] Registration creates only `OWNER` accounts (`ADMIN` cannot be self-registered).
- [ ] Owner booking -> charging start -> session completion -> simulated payment receipt flow works end-to-end.
- [ ] Live Web3Forms test submission from `/contact` arrives in the support email inbox and shows `SENT` in `/admin/enquiries`.
- [ ] Admin can manage stations, dispensers, users, enquiries, system health, and audit logs.

