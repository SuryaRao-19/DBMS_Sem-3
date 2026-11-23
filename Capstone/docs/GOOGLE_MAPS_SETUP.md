# Google Maps & Interactive Leaflet Fallback Guide

## 1. Dual-Engine Map Architecture (`app/static/js/ev_map.js`)

The landing page (`#landingMap`), station directory (`#stationsMap`), and station detail view (`#detailMap`) load coordinate-verified markers exclusively from MySQL (`/api/stations/map` or inline JSON on detail views).

- **Primary Engine (when `GOOGLE_MAPS_API_KEY` is configured)**: Dynamically loads Google Maps JavaScript API (`libraries=places`) with interactive info windows showing verification badges, demo bay status disclaimers, Haversine distance sorting ("Near Me"), and external `Directions` links.
- **Automatic Zero-Key Fallback (when `GOOGLE_MAPS_API_KEY` is blank or restricted/unavailable)**: Automatically initializes **Leaflet.js + OpenStreetMap** tiles with identical marker popups, Haversine user geolocation sorting, and zero console crash.

---

## 2. Securing `GOOGLE_MAPS_API_KEY` in Google Cloud Console

1. Create or select a Google Cloud project and enable **Maps JavaScript API** and **Places API**.
2. Create an API Key under **APIs & Services > Credentials**.
3. Apply **Application Restrictions > Websites (HTTP referrers)**:
   - `http://127.0.0.1:5000/*`
   - `http://localhost:5000/*`
   - `https://*.vercel.app/*` (or your custom production domain)
4. Apply **API Restrictions > Restrict key** strictly to:
   - **Maps JavaScript API**
   - **Places API**
5. Add `GOOGLE_MAPS_API_KEY=your_restricted_browser_key` to `.env` or Vercel Environment Variables.
6. Keep `GOOGLE_MAPS_API_KEY` unrestricted **only** on localhost dev if temporary testing requires it; never commit real keys to Git.

