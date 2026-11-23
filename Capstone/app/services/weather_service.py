"""
Open-Meteo Weather Telemetry Service
Provides free, keyless current conditions and short hourly forecast for station coordinates.
Cached in MySQL ApiCache for 30 minutes per rounded grid cell.
"""
import os

from flask import current_app

from app.services.http_client import make_cache_key, request_json

DEFAULT_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

WMO_WEATHER_CODES = {
    0: ("Clear sky", "fa-sun"),
    1: ("Mainly clear", "fa-sun"),
    2: ("Partly cloudy", "fa-cloud-sun"),
    3: ("Overcast", "fa-cloud"),
    45: ("Fog", "fa-smog"),
    48: ("Depositing rime fog", "fa-smog"),
    51: ("Light drizzle", "fa-cloud-rain"),
    53: ("Moderate drizzle", "fa-cloud-rain"),
    55: ("Dense drizzle", "fa-cloud-rain"),
    61: ("Slight rain", "fa-cloud-rain"),
    63: ("Moderate rain", "fa-cloud-showers-heavy"),
    65: ("Heavy rain", "fa-cloud-showers-heavy"),
    71: ("Slight snow fall", "fa-snowflake"),
    73: ("Moderate snow fall", "fa-snowflake"),
    75: ("Heavy snow fall", "fa-snowflake"),
    80: ("Slight rain showers", "fa-cloud-sun-rain"),
    81: ("Moderate rain showers", "fa-cloud-showers-heavy"),
    82: ("Violent rain showers", "fa-cloud-showers-heavy"),
    95: ("Thunderstorm", "fa-bolt"),
    96: ("Thunderstorm with slight hail", "fa-bolt"),
    99: ("Thunderstorm with heavy hail", "fa-bolt"),
}


def describe_wmo_code(code):
    try:
        key = int(code)
    except (TypeError, ValueError):
        return ("Unknown conditions", "fa-cloud")
    return WMO_WEATHER_CODES.get(key, (f"Weather code {key}", "fa-cloud"))


def _open_meteo_url():
    url = (
        (current_app.config.get("OPEN_METEO_BASE_URL") if current_app else None)
        or os.getenv("OPEN_METEO_BASE_URL")
        or DEFAULT_OPEN_METEO_URL
    )
    return str(url).strip()


def get_station_weather(latitude, longitude):
    """Fetch current weather + short hourly forecast from Open-Meteo (30-min MySQL cache)."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "error": "Station coordinates are not yet verified for weather lookup.",
            "attribution": OPEN_METEO_ATTRIBUTION,
        }

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return {"ok": False, "error": "Coordinates out of bounds.", "attribution": OPEN_METEO_ATTRIBUTION}

    # Round to ~110m grid so nearby probes share the 30-min cache responsibly
    grid_lat = round(lat, 3)
    grid_lng = round(lng, 3)
    cache_key = make_cache_key("open_meteo", grid_lat, grid_lng)

    res = request_json(
        provider="OpenMeteo",
        operation="station_forecast",
        url=_open_meteo_url(),
        params={
            "latitude": grid_lat,
            "longitude": grid_lng,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "forecast_hours": 12,
            "timezone": "auto",
        },
        timeout=8,
        max_retries=2,
        cache_key=cache_key,
        cache_ttl_seconds=1800,
    )

    if not res["ok"] or not isinstance(res["data"], dict):
        return {
            "ok": False,
            "error": f"Live weather telemetry temporarily unavailable ({res.get('error')}).",
            "attribution": OPEN_METEO_ATTRIBUTION,
        }

    payload = res["data"]
    current = payload.get("current") or {}
    hourly = payload.get("hourly") or {}
    wmo_label, wmo_icon = describe_wmo_code(current.get("weather_code"))

    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    rain_probs = hourly.get("precipitation_probability") or []
    codes = hourly.get("weather_code") or []

    forecast_points = []
    for idx in range(0, min(len(times), 12), 2):
        h_label, h_icon = describe_wmo_code(codes[idx] if idx < len(codes) else None)
        forecast_points.append(
            {
                "time": str(times[idx])[-5:] if len(str(times[idx])) >= 5 else str(times[idx]),
                "temperature_c": temps[idx] if idx < len(temps) else None,
                "rain_probability_pct": rain_probs[idx] if idx < len(rain_probs) else None,
                "condition": h_label,
                "icon": h_icon,
            }
        )

    rain_prob_now = rain_probs[0] if rain_probs else None

    return {
        "ok": True,
        "cached": res["cached"],
        "latitude": grid_lat,
        "longitude": grid_lng,
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
            "rain_probability_pct": rain_prob_now,
            "weather_code": current.get("weather_code"),
            "condition": wmo_label,
            "icon": wmo_icon,
            "observed_at": current.get("time"),
        },
        "hourly_forecast": forecast_points,
        "attribution": OPEN_METEO_ATTRIBUTION,
    }

