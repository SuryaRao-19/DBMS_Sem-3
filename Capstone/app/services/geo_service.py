"""
Maps, Geocoding, Reverse Geocoding & Routing Service
Powered by OpenStreetMap Nominatim + Project OSRM with MySQL caching & usage policy throttling.
NEVER used for keystroke autocomplete on public Nominatim.
"""
import math
import os

from flask import current_app

from app.services.http_client import make_cache_key, request_json
from app.services.station_service import get_all_stations

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
DEFAULT_OSRM_BASE = "https://router.project-osrm.org"

OSM_ATTRIBUTION = "Data © OpenStreetMap contributors (ODbL 1.0)"
OSRM_ATTRIBUTION = "Routing by Project OSRM · Map data © OpenStreetMap contributors"


def _nominatim_headers():
    ua = (
        (current_app.config.get("NOMINATIM_USER_AGENT") if current_app else None)
        or os.getenv("NOMINATIM_USER_AGENT")
        or "EZChargeNetworkPortal/1.0 (academic-ev-demo)"
    )
    return {
        "User-Agent": str(ua).strip(),
        "Accept": "application/json",
        "Accept-Language": "en-IN,en;q=0.9",
    }


def _osrm_base_url():
    base = (
        (current_app.config.get("OSRM_BASE_URL") if current_app else None)
        or os.getenv("OSRM_BASE_URL")
        or DEFAULT_OSRM_BASE
    )
    return str(base).strip().rstrip("/")


def haversine_km(lat1, lng1, lat2, lng2):
    """Compute great-circle distance between two WGS84 coordinates in kilometers."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_address(query, limit=5, country_codes="in"):
    """
    Explicit-submit address lookup using OpenStreetMap Nominatim.
    Respects 1 req/sec policy, descriptive User-Agent, and 24-hour MySQL response caching.
    """
    clean_q = " ".join((query or "").split())
    if len(clean_q) < 3:
        return {
            "ok": False,
            "error": "Enter at least 3 characters and submit search explicitly.",
            "results": [],
            "attribution": OSM_ATTRIBUTION,
        }

    limit = max(1, min(int(limit or 5), 10))
    cache_key = make_cache_key("nominatim_search", clean_q.lower(), country_codes, limit)

    res = request_json(
        provider="Nominatim",
        operation="geocode_search",
        url=NOMINATIM_SEARCH_URL,
        params={
            "q": clean_q,
            "format": "jsonv2",
            "addressdetails": 1,
            "countrycodes": country_codes,
            "limit": limit,
        },
        headers=_nominatim_headers(),
        timeout=10,
        max_retries=1,
        cache_key=cache_key,
        cache_ttl_seconds=86400,
        min_interval_seconds=1.05,
    )

    if not res["ok"]:
        return {
            "ok": False,
            "error": f"Address lookup temporarily unavailable ({res['error']}).",
            "results": [],
            "attribution": OSM_ATTRIBUTION,
        }

    items = res["data"] if isinstance(res["data"], list) else []
    normalized = []
    for item in items:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        addr = item.get("address") or {}
        normalized.append(
            {
                "display_name": item.get("display_name", clean_q),
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county"),
                "state": addr.get("state"),
                "postcode": addr.get("postcode"),
                "category": item.get("category"),
                "type": item.get("type"),
            }
        )

    return {
        "ok": True,
        "cached": res["cached"],
        "query": clean_q,
        "results": normalized,
        "attribution": OSM_ATTRIBUTION,
    }


def reverse_geocode(latitude, longitude):
    """Reverse-geocode coordinates into a structured address via Nominatim (1 req/sec + 24h cache)."""
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid latitude or longitude.", "attribution": OSM_ATTRIBUTION}

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return {"ok": False, "error": "Coordinates out of range.", "attribution": OSM_ATTRIBUTION}

    rlat, rlon = round(lat, 5), round(lon, 5)
    cache_key = make_cache_key("nominatim_reverse", rlat, rlon)

    res = request_json(
        provider="Nominatim",
        operation="reverse_geocode",
        url=NOMINATIM_REVERSE_URL,
        params={
            "lat": rlat,
            "lon": rlon,
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
        },
        headers=_nominatim_headers(),
        timeout=10,
        max_retries=1,
        cache_key=cache_key,
        cache_ttl_seconds=86400,
        min_interval_seconds=1.05,
    )

    if not res["ok"] or not isinstance(res["data"], dict):
        return {
            "ok": False,
            "error": res.get("error") or "Reverse geocoding failed.",
            "latitude": rlat,
            "longitude": rlon,
            "attribution": OSM_ATTRIBUTION,
        }

    data = res["data"]
    addr = data.get("address") or {}
    return {
        "ok": True,
        "cached": res["cached"],
        "latitude": rlat,
        "longitude": rlon,
        "display_name": data.get("display_name", f"{rlat}, {rlon}"),
        "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county"),
        "state": addr.get("state"),
        "postcode": addr.get("postcode"),
        "country": addr.get("country"),
        "attribution": OSM_ATTRIBUTION,
    }


def calculate_route(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Fetch driving route, distance, duration, GeoJSON polyline & turn steps from OSRM.
    Caches 6 hours in MySQL and degrades cleanly to Haversine estimate on OSRM outage.
    """
    try:
        olat, olng = float(origin_lat), float(origin_lng)
        dlat, dlng = float(dest_lat), float(dest_lng)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Valid origin and destination coordinates are required."}

    if not (-90 <= olat <= 90 and -180 <= olng <= 180 and -90 <= dlat <= 90 and -180 <= dlng <= 180):
        return {"ok": False, "error": "Route coordinates out of WGS84 bounds."}

    straight_km = round(haversine_km(olat, olng, dlat, dlng), 2)
    osm_dir_url = (
        f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_car"
        f"&route={olat:.5f}%2C{olng:.5f}%3B{dlat:.5f}%2C{dlng:.5f}"
    )

    cache_key = make_cache_key("osrm_route", round(olat, 4), round(olng, 4), round(dlat, 4), round(dlng, 4))
    url = f"{_osrm_base_url()}/route/v1/driving/{olng:.6f},{olat:.6f};{dlng:.6f},{dlat:.6f}"

    res = request_json(
        provider="OSRM",
        operation="driving_route",
        url=url,
        params={
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
        },
        timeout=10,
        max_retries=1,
        cache_key=cache_key,
        cache_ttl_seconds=21600,
        min_interval_seconds=0.25,
    )

    if res["ok"] and isinstance(res["data"], dict) and res["data"].get("routes"):
        route = res["data"]["routes"][0]
        distance_km = round(float(route.get("distance", 0)) / 1000.0, 2)
        duration_min = max(1, int(round(float(route.get("duration", 0)) / 60.0)))
        geometry = route.get("geometry") or {}

        steps = []
        for leg in (route.get("legs") or [])[:1]:
            for step in (leg.get("steps") or [])[:18]:
                maneuver = step.get("maneuver") or {}
                road = (step.get("name") or "").strip() or "local road"
                m_type = (maneuver.get("type") or "continue").replace("_", " ").capitalize()
                mod = (maneuver.get("modifier") or "").replace("_", " ").strip()
                instruction = f"{m_type} {mod} onto {road}".replace("  ", " ").strip()
                steps.append(
                    {
                        "instruction": instruction,
                        "distance_m": int(round(float(step.get("distance") or 0))),
                    }
                )

        return {
            "ok": True,
            "fallback_mode": False,
            "cached": res["cached"],
            "distance_km": distance_km,
            "duration_min": duration_min,
            "straight_line_km": straight_km,
            "geometry": geometry,
            "steps": steps,
            "osm_directions_url": osm_dir_url,
            "attribution": OSRM_ATTRIBUTION,
        }

    # Graceful Haversine fallback when public OSRM demo server is unavailable
    est_min = max(2, int(round((straight_km / 32.0) * 60.0)))
    return {
        "ok": True,
        "fallback_mode": True,
        "cached": False,
        "distance_km": straight_km,
        "duration_min": est_min,
        "straight_line_km": straight_km,
        "geometry": {
            "type": "LineString",
            "coordinates": [[olng, olat], [dlng, dlat]],
        },
        "steps": [
            {
                "instruction": "OSRM demo router temporarily unavailable; showing straight-line reference corridor.",
                "distance_m": int(round(straight_km * 1000)),
            }
        ],
        "osm_directions_url": osm_dir_url,
        "attribution": f"Fallback great-circle estimate ({res.get('error') or 'OSRM unavailable'})",
    }


def find_nearby_stations(latitude, longitude, radius_km=35.0, limit=15):
    """Return coordinate-verified charging stations sorted by distance from (latitude, longitude)."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return []

    radius_km = max(1.0, min(float(radius_km or 35.0), 500.0))
    limit = max(1, min(int(limit or 15), 50))

    stations = get_all_stations()
    nearby = []
    for st in stations:
        if st.get("latitude") is None or st.get("longitude") is None:
            continue
        dist = haversine_km(lat, lng, float(st["latitude"]), float(st["longitude"]))
        if dist <= radius_km:
            item = dict(st)
            item["distance_km"] = round(dist, 2)
            nearby.append(item)

    nearby.sort(key=lambda s: s["distance_km"])
    return nearby[:limit]

