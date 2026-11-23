# Data Sources & Provenance Governance

## 1. Strict Three-Tier Record Separation

All metrics and database records in **EZ Charge Network Portal** are classified into one of three non-overlapping categories:

1. **Type A — Official Company Disclosures (`OFFICIAL_COMPANY_SOURCE`)**
   - Publicly verified figures issued by **The Tata Power Company Limited / Tata Power EZ Charge**.
   - **Primary Baseline (Oct 12, 2026 Press Release)**:
     - **6,700+** public, semi-public, and captive EV charging points
     - **2.5 lakh+** residential home chargers installed
     - **1,200+** e-bus charging points across transit depots
     - **7 lakh+** registered EZ Charge customers
     - **700+** cities across India
   - **Documented Scope Conflict Reconciliation**: Earlier Tata Power EZ Charge portal pages reported **5,500+** public/captive charging points across **620+** cities. Rather than silently picking one figure or blending them, the platform preserves both with publication dates (`published_at`) and inclusion-scope notes (public + semi-public + captive vs public-only snapshot).
   - **Official Consumer App & Channel Links**:
     - Google Play Store: `https://play.google.com/store/apps/details?id=com.tatapower.evapp`
     - Apple App Store: `https://apps.apple.com/in/app/tata-power-ez-charge/id1496350476`
     - Corporate Channels: `x.com/tatapower`, `youtube.com/@TataPowerCompanyLtd`, `linkedin.com/company/tata-power/`, `instagram.com/tatapowercompanyltd/`, `facebook.com/tatapower/`, `tatapower.com/ezcharge/`

2. **Type B — Synthetic Academic Demonstration Data (`DEMONSTRATION_SEED`)**
   - Sample EV owner accounts (`@example.test`), vehicles, simulated dispenser occupancy states, bookings, charging meter kWh totals, and Test Mode ledger transactions (`Payments`).
   - Dispenser availability (`AVAILABLE` / `OCCUPIED`) and EV owner earnings/spend figures carry explicit UI notices (`"Availability not connected — demonstration data."` and `"Simulated earnings — not actual company revenue."`).

3. **Type C — Live Portal Runtime Records (`USER_SUBMITTED` / `SYSTEM_GENERATED`)**
   - Enquiries submitted via `/contact`, QR scan counters (`StationQRCodes`), audit logs (`AuditLogs`), newly registered portal accounts, and Admin station verification updates.

---

## 2. Database Provenance Columns (Migration 006)

`Stations` and `DataSources` store full audit metadata:
- `source_type` (e.g., `OFFICIAL_PRESS_RELEASE`, `PUBLIC_DIRECTORY`)
- `source_name` (publisher label)
- `source_url` (clickable primary source link)
- `published_at` / `retrieved_at` / `last_verified_at`
- `confidence_level` (`HIGH`, `MEDIUM`, `LOW`)
- `record_origin` (`OFFICIAL_COMPANY_SOURCE`, `VERIFIED_PUBLIC_SOURCE`, `GOOGLE_PLACES_REFERENCE`, `DEMONSTRATION_SEED`, `USER_SUBMITTED`, `SYSTEM_GENERATED`)
- `verification_status` (`VERIFIED`, `PENDING_VERIFICATION`, `PENDING_REVIEW`, `HISTORICAL`, `DEMO`, `ESTIMATED`, `UNAVAILABLE`, `OUTDATED`)

