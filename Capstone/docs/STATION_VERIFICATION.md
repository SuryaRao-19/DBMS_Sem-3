# Station Verification & Coordinate Integrity Policy

## 1. Zero Fabricated Coordinates Rule

No charging station coordinates are guessed or interpolated from city centroids or street names.

- **Verified Coordinate Hubs (`VERIFIED`)**:
  - Stations with verified street addresses, PIN codes, and latitude/longitude (including **Dr. Ambedkar International Centre, 15 Janpath Rd, New Delhi 110001** ~ `28.6200, 77.2100`, inaugurated Apr 2023, and curated Delhi NCR reference stations) plot as pins on Google Maps / Leaflet and expose external Google Maps `Directions` links.
- **Unverified Candidate Locations (`PENDING_VERIFICATION`)**:
  - Press-release and highway-corridor announcements where exact GPS coordinates could not be independently pinned (e.g., Yamuna Expressway E-Highway corridor, Kanpur, Hyderabad, Suryapet, Narketpalle, Leela Mumbai hospitality hub candidates) are seeded in MySQL with `latitude = NULL`, `longitude = NULL`, and `verification_status = 'PENDING_VERIFICATION'`.

---

## 2. Strict Map Feed Gate (`/api/stations/map`)

In `app/routes/api.py`, `stations_map_feed()` explicitly filters out any station where:
- `latitude IS NULL OR longitude IS NULL`, OR
- `verification_status IN ('PENDING_VERIFICATION', 'PENDING_REVIEW', 'OUTDATED')`.

On `/stations` and `/stations/<id>`, candidate stations render an explicit notice:
> **"Location verification pending."**
and suppress `Directions` links and map containers until an administrator validates coordinates.

---

## 3. Admin Verification Workflow (`/admin/stations`)

Administrators review candidate hubs, uploaded CSV batches, and coordinate updates using:
- `POST /admin/stations/<station_id>/verify` — transitions `verification_status` between `VERIFIED`, `PENDING_VERIFICATION`, `HISTORICAL`, and `OUTDATED`.
- Every transition is persisted in `AuditLogs` via `log_audit_event()` with admin `user_id` and source metadata.

