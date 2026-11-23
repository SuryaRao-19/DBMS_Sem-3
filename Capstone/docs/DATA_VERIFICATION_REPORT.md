# EV ChargeNet — Real-World Data Verification & Integrity Report

> **Independent Platform Disclaimer:** **EV ChargeNet** is an independent academic and full-stack software engineering demonstration that models its station geography and corporate identity architecture on **Tata Power EZ Charge** publicly verifiable information as a reference case study. It is **not** affiliated with, endorsed by, or officially operated by The Tata Power Company Limited.

---

## 1. Reference Company & Official Sources

| Attribute | Verified Value | Data Status | Primary Source URL |
| :--- | :--- | :--- | :--- |
| **Reference Operator** | Tata Power EZ Charge (The Tata Power Company Limited) | `VERIFIED` | https://www.tatapower.com/ezcharge/ |
| **Network Coverage & Scale** | 5,500+ public & captive charging points, 620+ cities & towns covered (700+ India reach), 1.2 Lakh+ home chargers, 1,200+ e-bus charging points | `VERIFIED` | https://www.tatapower.com/ezcharge/ |
| **Mobile App & Ecosystem Links** | Official EZ Charge Android App (`com.tatapower.ezcharge`) & Official Linktree | `VERIFIED` | https://play.google.com/store/apps/details?id=com.tatapower.ezcharge |
| **24x7 Support Helpline** | `1800 833 2233` (Toll-Free) | `VERIFIED` | https://www.tatapower.com/ezcharge/ |
| **Support Email** | `evsupport@tatapower.com` | `VERIFIED` | https://www.tatapower.com/ezcharge/ |
| **Corporate Vision** | *"Empower a billion lives through sustainable, affordable and innovative energy solutions."* | `VERIFIED` | https://www.tatapower.com/ |
| **Mission & Values** | Leadership with Care: Customer Centricity, Operational Excellence, Sustainable Growth, Empowered Workforce, Stakeholder Responsibility | `VERIFIED` | https://www.tatapower.com/ |

---

## 2. Official Social Media Links (`SocialLinks` Table)

Tata Power EZ Charge announcements and updates are published through Tata Power's official parent corporate profiles:

| Platform | Handle / Label | Verified Official URL | Status |
| :--- | :--- | :--- | :--- |
| **Official Portal** | `tatapower.com/ezcharge` | https://www.tatapower.com/ezcharge/ | `VERIFIED` |
| **LinkedIn** | `Tata Power` | https://www.linkedin.com/company/tata-power/ | `VERIFIED` |
| **Instagram** | `@tatapowercompanyltd` | https://www.instagram.com/tatapowercompanyltd/ | `VERIFIED` |
| **X (Twitter)** | `@TataPower` | https://x.com/TataPower | `VERIFIED` |
| **YouTube** | `@tatapower` | https://www.youtube.com/@tatapower | `VERIFIED` |
| **Facebook** | `tatapower` | https://www.facebook.com/tatapower/ | `VERIFIED` |

---

## 3. Data Source Register (`DataSources` Table)

| Data Item | Source | Source URL | Verification Date | Data Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pan-India Network Reach (700+ cities)** | Tata Power Official EZ Charge Portal | https://www.tatapower.com/ezcharge/ | 2026-11-12 | `VERIFIED` | Published public & residential EV footprint. |
| **Helpline (`1800 833 2233`) & Email (`evsupport@tatapower.com`)** | Tata Power Customer Support | https://www.tatapower.com/ezcharge/ | 2026-11-12 | `VERIFIED` | Displayed in About Us & Contact Us views (no fabricated support addresses). |
| **Vision, Mission & TATA Values** | Tata Power Corporate Overview | https://www.tatapower.com/ | 2026-11-12 | `VERIFIED` | Used verbatim with academic attribution. |
| **Corporate Social Media Handles** | Tata Power Official Channels | https://www.tatapower.com/ | 2026-11-12 | `VERIFIED` | Linked in footer & About Us with `target="_blank" rel="noopener noreferrer"`. |
| **Delhi NCR Station Locations, PINs & GPS** | Tata Power EZ Charge / PlugShare / Statiq / Municipal Grids | https://www.tatapower.com/ezcharge/ | 2026-11-12 | `VERIFIED` | Physical NCR addresses, PINs, and coordinates across 6 regions. |
| **Live Physical Dispenser Bay Occupancy** | Independent Academic Platform Status | N/A | 2026-11-12 | `UNAVAILABLE` | Live OCPP hardware telemetry requires commercial operator API credentials. |
| **Slot Bookings & Energy Meter Simulator** | EV ChargeNet MySQL Sandbox | N/A | 2026-11-12 | `DEMO` | Transactional InnoDB row locks and stored procedures run on project MySQL records. |
| **Session Duration & Cost Preview** | EV ChargeNet Tariff Estimator | N/A | 2026-11-12 | `ESTIMATED` | `Hours × Dispenser kW × Tariff (₹/kWh)`; actual station tariffs vary. |
| **Payment Settlements & Invoices** | EV ChargeNet Simulated Ledger | N/A | 2026-11-12 | `DEMO` | Zero real money charged; no card/UPI credentials stored. |

---

## 4. Verified Delhi NCR Charging Hubs (14 Active Hubs across 6 Regions)

All 14 hubs reside in `Stations` (`verification_status='VERIFIED'`, `approval_status='APPROVED'`) alongside corresponding `ChargingPoints` and `StationFacilities`:

| # | Station Name | City (NCR Region) | Postal Code | Coordinates (Lat, Lng) | Capacity & Connectors | Source URL |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Connaught Place EV Hub | New Delhi | 110001 | `28.6280000, 77.2090000` | 60 kW DC / 22 kW AC (`CCS2, CHAdeMO, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 2 | Tata Power EZ Charge — Rohini Sec 10 | New Delhi | 110085 | `28.7219000, 77.1110000` | 30 kW DC / 22 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 3 | Tata Power EZ Charge — Safdarjung Enclave | New Delhi | 110029 | `28.5712000, 77.1903000` | 30 kW DC / 7.4 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 4 | Gurugram Central Charge | Gurugram | 122001 | `28.4669000, 77.0648000` | 120 kW / 50 kW DC (`CCS2, CHADEMO`) | https://www.tatapower.com/ezcharge/ |
| 5 | Tata Power EZ Charge — Airia Mall | Gurugram | 122101 | `28.3825750, 77.0518260` | 50 kW DC / 22 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 6 | Tata Power EZ Charge — Ardee Mall | Gurugram | 122002 | `28.4594970, 77.0266380` | 30 kW DC / 22 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 7 | Noida Green Charge | Noida | 201301 | `28.5695000, 77.3222000` | 60 kW DC / 22 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 8 | Tata Power EZ Charge — Ginger Hotel Sec 63 | Noida | 201301 | `28.6268000, 77.3753000` | 30 kW DC / 7.4 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 9 | Tata Power EZ Charge — Pari Chowk | Greater Noida | 201310 | `28.4745000, 77.5039000` | 30 kW DC / 22 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 10 | Tata Power EZ Charge — India Expo Mart | Greater Noida | 201306 | `28.4674000, 77.4872000` | 60 kW DC (`CCS2`) | https://www.tatapower.com/ezcharge/ |
| 11 | Tata Power EZ Charge — High Street Sec 81 | Faridabad | 121007 | `28.3929000, 77.3402000` | 30 kW DC (`CCS2`) | https://www.tatapower.com/ezcharge/ |
| 12 | Tata Power EZ Charge — Taj Surajkund | Faridabad | 121009 | `28.3998000, 77.2962000` | 30 kW DC / 22 kW AC (`CCS2, TYPE2`) | https://www.tatapower.com/ezcharge/ |
| 13 | Tata Power EZ Charge — Shipra Suncity | Ghaziabad | 201014 | `28.6380000, 77.3680000` | 30 kW DC (`CCS2`) | https://www.tatapower.com/ezcharge/ |
| 14 | Tata Power EZ Charge — Pacific Mall Sahibabad | Ghaziabad | 201010 | `28.6480000, 77.3320000` | 25 kW DC / 22 kW AC (`CCS2, CHADEMO, TYPE2`) | https://www.tatapower.com/ezcharge/ |

---

## 5. Interactive Map & API Key Security (`GOOGLE_MAPS_API_KEY`)

1. **Dual-Engine Interactive Map (`app/static/js/ev_map.js`)**:
   - Powered dynamically from MySQL via `GET /api/stations/map` (only `APPROVED` + `ACTIVE` hubs).
   - **Primary Engine**: When `GOOGLE_MAPS_API_KEY` is configured in `.env` or Vercel Environment Variables, renders Google Maps JavaScript API markers, info windows, Directions links, and browser geolocation *"Near Me"* sorting.
   - **Automatic Fallback**: When `GOOGLE_MAPS_API_KEY` is blank or Google Maps fails to initialize, seamlessly activates **Leaflet.js + OpenStreetMap** with identical pins, filters, and *"Near Me"* Haversine distance sorting — zero broken UI.
2. **Mandatory Key Restrictions (if enabling Google Maps)**:
   - Never hardcode keys into source control (`.env` is gitignored).
   - In Google Cloud Console -> *APIs & Services* -> *Credentials*, restrict your browser key:
     - **Application restrictions**: `HTTP referrers (web sites)` allowing only your production Vercel domain (`https://<your-app>.vercel.app/*`) and local dev (`http://127.0.0.1:5000/*`).
     - **API restrictions**: Restrict key to **Maps JavaScript API** (and **Places API** if enabled).

---

## 6. CSV Import & Admin Approval Gate

- Endpoint: `POST /admin/stations/import` (`app/services/station_import_service.py`).
- Validates station name, address, city, 6-digit Indian PIN code (`^\d{6}$`), Indian geographic bounds (`6–38°N`, `68–98°E`), and valid `http/https` `source_url`.
- Automatically skips duplicate stations (matching station name OR proximity within ~100m).
- Forces `approval_status = 'PENDING_APPROVAL'` by default so unapproved submissions never appear on `/stations` or `/api/stations/map` until an Administrator reviews them via `POST /admin/stations/<id>/review`.

---

## 7. Database Architecture Determination (MySQL 8.0+ Retained)

- **Inspected Existing Architecture**: `ev_charging_db` on **MySQL 8.0+ (InnoDB)** with 14 normalized tables, composite B-Tree indexes, stored function `CalculateChargingCost`, stored procedure `CompleteChargingSession`, trigger `trg_booking_before_insert`, and SQL migrations `001`–`004` (`app/db.py` via `PyMySQL` + `DBUtils.PooledDB`).
- **Decision**: Retain **MySQL 8.0+** exclusively. `parse_database_url()` enforces `mysql` / `mysql+pymysql` schemes so PostgreSQL and MySQL SQL dialects are never mixed, and the runtime never attempts to connect to MySQL using Supabase credentials.
- **Credential & Authorization Boundaries**:
  - `.env` and `.env.example` define `SUPABASE_URL=`, `SUPABASE_PUBLISHABLE_KEY=`, and `WEB3FORMS_ACCESS_KEY=`.
  - Any Supabase publishable key is strictly client metadata and **never** substitutes for server-side RBAC, ownership verification, CSRF enforcement, or database row-level authorization; privileged service-role credentials must never appear in frontend templates or JavaScript.

---

## 8. Charging Tariff Disclosure (`DEMO` / `ESTIMATED`)

- Tata Power EZ Charge does **not** publish a single nationwide flat per-kWh tariff; live site pricing depends on state DISCOM tariffs, site parking/hosting, charger output (AC vs DC fast), and GST, and is displayed inside the official Tata Power EZ Charge mobile app before session initiation.
- Across Delhi/India public networks, AC public charging typically spans ~₹8–₹15/kWh and DC fast charging ~₹15–₹25+/kWh.
- All dispenser tariff rates displayed on EV ChargeNet (`ChargingPoints.tariff_per_kwh`) are explicitly labelled **Demo Tariff Rate** (`DEMO` / `ESTIMATED`), and all financial transactions run strictly in **DEMO ONLY** mode with no real money charged.


