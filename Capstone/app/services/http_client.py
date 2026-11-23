"""
Shared Resilient HTTP Client, Rate-Limiter, Retry Logic & MySQL Cache Helper
Supports Open Charge Map, OpenStreetMap Nominatim, OSRM, Open-Meteo & India Postal PIN APIs.
"""
import hashlib
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from app.db import execute, query_one

_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = {}

DEFAULT_HTTP_HEADERS = {
    "User-Agent": "EZChargeNetworkPortal/1.0 (academic-ev-demo; +https://github.com)",
    "Accept": "application/json",
}

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_cache_key(prefix, *parts):
    """Build a bounded deterministic cache key under 160 chars."""
    raw = "|".join(str(p or "").strip() for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    safe_prefix = "".join(ch if ch.isalnum() or ch in ("_", "-", ":") else "_" for ch in str(prefix))[:40]
    return f"{safe_prefix}:{digest}"


def get_cached_payload(cache_key):
    """Fetch a non-expired JSON payload from MySQL ApiCache, degrading safely if DB/table unavailable."""
    if not cache_key:
        return None
    try:
        row = query_one(
            "SELECT payload_json, fetched_at, expires_at FROM ApiCache WHERE cache_key = %s AND expires_at > UTC_TIMESTAMP()",
            (cache_key,),
        )
        if not row or not row.get("payload_json"):
            return None
        return json.loads(row["payload_json"])
    except Exception:
        return None


def set_cached_payload(cache_key, provider, payload, ttl_seconds):
    """Persist JSON payload into MySQL ApiCache with TTL seconds."""
    if not cache_key or ttl_seconds <= 0:
        return
    try:
        now = _utc_now()
        expires = now + timedelta(seconds=int(ttl_seconds))
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        execute(
            """
            INSERT INTO ApiCache (cache_key, provider, payload_json, fetched_at, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                provider = VALUES(provider),
                payload_json = VALUES(payload_json),
                fetched_at = VALUES(fetched_at),
                expires_at = VALUES(expires_at)
            """,
            (cache_key, str(provider)[:60], encoded, now, expires),
        )
    except Exception:
        # Cache writes must never crash foreground user flows
        pass


def record_api_log(
    provider,
    operation,
    status,
    http_status=None,
    records_fetched=0,
    records_imported=0,
    duplicates_detected=0,
    latency_ms=None,
    error_message=None,
):
    """Persist an external API call outcome to ApiIntegrationLogs without failing the caller."""
    try:
        execute(
            """
            INSERT INTO ApiIntegrationLogs (
                provider, operation, status, http_status,
                records_fetched, records_imported, duplicates_detected,
                latency_ms, error_message
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(provider)[:60],
                str(operation)[:80],
                status,
                http_status,
                int(records_fetched or 0),
                int(records_imported or 0),
                int(duplicates_detected or 0),
                int(latency_ms) if latency_ms is not None else None,
                str(error_message)[:490] if error_message else None,
            ),
        )
    except Exception:
        pass


def _respect_rate_limit(provider, min_interval_seconds):
    """Enforce per-provider minimum delay between outbound HTTP requests."""
    if not min_interval_seconds or min_interval_seconds <= 0:
        return
    with _RATE_LOCK:
        now = time.monotonic()
        last_ts = _LAST_REQUEST_AT.get(provider)
        if last_ts is not None:
            wait_for = min_interval_seconds - (now - last_ts)
            if wait_for > 0:
                time.sleep(wait_for)
        _LAST_REQUEST_AT[provider] = time.monotonic()


def request_json(
    provider,
    operation,
    url,
    params=None,
    headers=None,
    timeout=10,
    max_retries=2,
    backoff_base_seconds=0.4,
    cache_key=None,
    cache_ttl_seconds=0,
    min_interval_seconds=0.0,
    log_success=True,
):
    """
    Execute an HTTP GET expecting JSON with:
      1. Optional MySQL ApiCache lookup before outbound HTTP.
      2. Per-provider rate-limit pacing (e.g., 1.05s for Nominatim).
      3. Timeout protection and bounded exponential backoff retries on transient failures.
      4. Automatic telemetry logging in ApiIntegrationLogs.
    Returns: {"ok": bool, "data": any, "cached": bool, "http_status": int|None, "error": str|None, "latency_ms": int}
    """
    if cache_key:
        cached = get_cached_payload(cache_key)
        if cached is not None:
            return {
                "ok": True,
                "data": cached,
                "cached": True,
                "http_status": 200,
                "error": None,
                "latency_ms": 0,
            }

    merged_headers = dict(DEFAULT_HTTP_HEADERS)
    if headers:
        merged_headers.update(headers)

    last_status = None
    last_error = None
    started_at = time.monotonic()

    for attempt in range(max_retries + 1):
        _respect_rate_limit(provider, min_interval_seconds)
        try:
            resp = requests.get(
                url,
                params=params,
                headers=merged_headers,
                timeout=timeout,
            )
            last_status = resp.status_code

            if resp.status_code == 200:
                payload = resp.json()
                latency_ms = int((time.monotonic() - started_at) * 1000)
                if cache_key and cache_ttl_seconds > 0:
                    set_cached_payload(cache_key, provider, payload, cache_ttl_seconds)
                if log_success:
                    record_api_log(
                        provider=provider,
                        operation=operation,
                        status="SUCCESS",
                        http_status=200,
                        latency_ms=latency_ms,
                    )
                return {
                    "ok": True,
                    "data": payload,
                    "cached": False,
                    "http_status": 200,
                    "error": None,
                    "latency_ms": latency_ms,
                }

            snippet = (resp.text or "").strip()[:240]
            last_error = f"HTTP {resp.status_code}: {snippet or resp.reason}"
            if resp.status_code not in RETRYABLE_STATUS_CODES:
                break

        except (requests.Timeout, requests.ConnectionError, ValueError) as exc:
            last_error = f"{exc.__class__.__name__}: {str(exc)[:220]}"

        if attempt < max_retries:
            time.sleep(backoff_base_seconds * (2 ** attempt))

    latency_ms = int((time.monotonic() - started_at) * 1000)
    log_status = "RATE_LIMITED" if last_status == 429 else "FAILED"
    record_api_log(
        provider=provider,
        operation=operation,
        status=log_status,
        http_status=last_status,
        latency_ms=latency_ms,
        error_message=last_error,
    )
    return {
        "ok": False,
        "data": None,
        "cached": False,
        "http_status": last_status,
        "error": last_error or "Upstream request failed",
        "latency_ms": latency_ms,
    }

