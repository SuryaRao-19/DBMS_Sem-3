# Free Public API Integrations, Rate Limits & Data Provenance

This document details all external free/open APIs integrated into the **EZ Charge Network Portal (Independent Academic Demo)**, their exact authentication requirements, attribution licenses, rate-limit safeguards, MySQL caching strategy, and third-party exclusions.

---

## 1. Provider Inventory & Operational Status

| Provider | Role in Portal | Authentication | Rate Limit & Caching Strategy | License / Attribution | Live Status Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Open Charge Map API v3** | External EV station POI sync (`countrycode=IN`) | `OPEN_CHARGE_MAP_API_KEY` (`X-API-Key` header) | On-demand Admin sync, retry/backoff, SHA-256 + coordinate deduplication | **CC BY 4.0** (Open Charge Map Contributors) | Returns **HTTP 403** when `OPEN_CHARGE_MAP_API_KEY` is omitted; sync skips safely (`SKIPPED_UNCONFIGURED`) |
| **ChargeAlong API** | Investigated secondary EV provider | N/A | Excluded cleanly after evaluation | N/A | **Excluded**: Covers AU, NZ, US, UK, and CA only — zero Indian station coverage |
| **OpenStreetMap + Leaflet** | Interactive EV station map tiles | Keyless | CDN Leaflet 1.9.4 + OSM tiles | **ODbL 1.0** (`© OpenStreetMap contributors`) | Always active without Google Maps key |
| **Nominatim (OSM)** | Explicit-submit address lookup & reverse geocoding | Descriptive `NOMINATIM_USER_AGENT` | **Strict 1.05s request interval + 24h MySQL `ApiCache`** | **ODbL 1.0** | **Never used for keystroke autocomplete** |
| **Project OSRM** | Driving route polyline, distance & turn directions | Keyless public demo server | **6h MySQL `ApiCache`** + automatic Haversine fallback | BSD 2-Clause / ODbL | Best-effort demo API; fallback corridor renders when unavailable |
| **Open-Meteo** | Station-coordinate temperature, rain prob, wind, 12h forecast | Keyless | Rounded 3-decimal grid cell + **30-min MySQL `ApiCache`** | **CC BY 4.0** (`Weather data by Open-Meteo.com`) | Non-commercial academic use; graceful message on outage |
| **PostalPinCode.in (India Post)** | 6-digit PIN lookup (State, District, Post Offices) | Keyless + `User-Agent` header | **7-day MySQL `ApiCache`** + `api.zippopotam.us/in` fallback | Public Indian Postal Reference | **1-to-many Post Offices preserved** (never assumes 1 PIN = 1 physical street address) |
| **Google OAuth 2.0 / OIDC** | Sign in with Google | `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET` | Authlib state + nonce validation | OAuth 2.0 / OpenID Connect | Optional; local email/password auth always works |
| **Web3Forms** | Public Contact Us enquiry proxy | `WEB3FORMS_ACCESS_KEY` | Server-side rate limiting + honeypot + MySQL backup | Web3Forms API | Every submission stored in `ContactMessages` |
| **Razorpay TEST MODE** | Academic billing & dynamic Payment QR | `RAZORPAY_KEY_ID` (`rzp_test_*`) & `RAZORPAY_KEY_SECRET` | Server HMAC-SHA256 verification only | Sandbox / Test Mode Only | Live keys (`rzp_live_*`) intentionally blocked |

---

## 2. Four-Way Data Provenance Governance

All platform records are separated cleanly across four categories (`Stations.provenance_category` & `DataSources.provenance_category`):

- **`A_OFFICIAL_DISCLOSURE`**: Published Tata Power EZ Charge press releases, scale counters, app store links, and NCR reference sites.
- **`B_THIRD_PARTY_API`**: Stations synced from Open Charge Map (`external_source_id`, `license_info`, `imported_at`, `last_synced_at`, `raw_payload_hash`) plus external OSM/OSRM/Open-Meteo/PIN metadata. Never claims real-time charger occupancy unless explicitly provided.
- **`C_LOCAL_DEMO`**: Academic seed demonstration accounts (`@example.test`), vehicles, and slot bookings (`is_demo = 1`).
- **`D_SIMULATED_TELEMETRY`**: Simulated charging energy sessions (kWh), dynamic billing, and Razorpay Test Mode / local sandbox transactions.

---

## 3. Extended Local `qrcode` Architecture

All QR images are generated dynamically in memory (`app/services/qr_service.py`) without filesystem writes (serverless safe):

1. **Station Identification QR** (`StationQRCodes`): `/qr/station/<token>` & `/qr/station/<token>/image.png`
2. **Charging Point Dispenser QR** (`PointQRCodes`): `/qr/point/<token>`, `/qr/point/<token>/image.png`, Admin rotation (`/admin/points/<id>/qr/regenerate`)
3. **Booking Check-In Verification QR** (`BookingQRCodes`): Strict owner/Admin RBAC on `/owner/bookings/<id>/qr.png` & `/qr/booking/<token>`
4. **Dynamic Payment QR** (`Payments`): Server-created Razorpay Test Mode QR / sandbox UPI QR (never marks payment success upon scan; requires verified payment callback/HMAC verification)

