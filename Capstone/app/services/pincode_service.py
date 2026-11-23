"""
Indian PIN Code Lookup & Validation Service
Queries PostalPinCode.in (India Post directory) with fallback to Zippopotam.us on upstream outage.
Explicitly preserves 1-to-many Post Office multiplicity (never assumes 1 PIN = 1 physical street address).
"""
import os
import re

from flask import current_app

from app.services.http_client import make_cache_key, request_json

DEFAULT_POSTAL_PIN_URL = "https://api.postalpincode.in/pincode"
ZIPPOPOTAM_IN_URL = "https://api.zippopotam.us/in"
PIN_REGEX = re.compile(r"^[1-9][0-9]{5}$")

POSTAL_PIN_DISCLAIMER = (
    "One Indian 6-digit PIN code often covers multiple Post Offices and localities. "
    "Use State/District/Post Office results as assisted metadata, not a single physical street coordinate."
)


def _postal_base_url():
    url = (
        (current_app.config.get("POSTAL_PIN_API_URL") if current_app else None)
        or os.getenv("POSTAL_PIN_API_URL")
        or DEFAULT_POSTAL_PIN_URL
    )
    return str(url).strip().rstrip("/")


def is_valid_indian_pin(pin_code):
    """Validate Indian 6-digit PIN format (first digit 1-9)."""
    return bool(PIN_REGEX.match((pin_code or "").strip()))


def lookup_indian_pincode(pin_code):
    """
    Validate a 6-digit Indian PIN code and return State, District, and ALL associated Post Offices.
    Caches successful responses 7 days in MySQL ApiCache.
    """
    pin = (pin_code or "").strip()
    if not is_valid_indian_pin(pin):
        return {
            "ok": False,
            "valid": False,
            "pin_code": pin,
            "error": "Enter a valid 6-digit Indian PIN code (first digit 1-9).",
            "post_offices": [],
            "disclaimer": POSTAL_PIN_DISCLAIMER,
        }

    cache_key = make_cache_key("india_pin", pin)
    res = request_json(
        provider="PostalPinCode",
        operation="pincode_lookup",
        url=f"{_postal_base_url()}/{pin}",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; EZChargeNetworkPortal/1.0)",
            "Accept": "application/json",
        },
        timeout=8,
        max_retries=1,
        cache_key=cache_key,
        cache_ttl_seconds=604800,
    )

    if res["ok"] and isinstance(res["data"], list) and res["data"]:
        envelope = res["data"][0]
        if envelope.get("Status") == "Success" and envelope.get("PostOffice"):
            offices = []
            for po in envelope["PostOffice"]:
                offices.append(
                    {
                        "name": po.get("Name"),
                        "branch_type": po.get("BranchType"),
                        "delivery_status": po.get("DeliveryStatus"),
                        "district": po.get("District"),
                        "division": po.get("Division"),
                        "region": po.get("Region"),
                        "block": po.get("Block"),
                        "state": po.get("State"),
                    }
                )
            primary = offices[0]
            return {
                "ok": True,
                "valid": True,
                "cached": res["cached"],
                "provider_used": "api.postalpincode.in",
                "pin_code": pin,
                "state": primary.get("state"),
                "district": primary.get("district"),
                "post_office_count": len(offices),
                "post_offices": offices,
                "message": envelope.get("Message") or f"{len(offices)} Post Office(s) mapped to PIN {pin}",
                "disclaimer": POSTAL_PIN_DISCLAIMER,
            }

        return {
            "ok": False,
            "valid": False,
            "pin_code": pin,
            "provider_used": "api.postalpincode.in",
            "error": f"No records found in India Post directory for PIN {pin}.",
            "post_offices": [],
            "disclaimer": POSTAL_PIN_DISCLAIMER,
        }

    # Secondary fallback when api.postalpincode.in is unreachable
    fallback = request_json(
        provider="PostalPinCodeFallback",
        operation="zippopotam_lookup",
        url=f"{ZIPPOPOTAM_IN_URL}/{pin}",
        timeout=6,
        max_retries=1,
        cache_key=make_cache_key("india_pin_zippo", pin),
        cache_ttl_seconds=604800,
    )
    if fallback["ok"] and isinstance(fallback["data"], dict) and fallback["data"].get("places"):
        places = fallback["data"]["places"]
        offices = [
            {
                "name": p.get("place name"),
                "branch_type": None,
                "delivery_status": None,
                "district": None,
                "division": None,
                "region": None,
                "block": None,
                "state": p.get("state"),
            }
            for p in places
        ]
        return {
            "ok": True,
            "valid": True,
            "cached": fallback["cached"],
            "provider_used": "api.zippopotam.us (fallback)",
            "pin_code": pin,
            "state": offices[0].get("state"),
            "district": None,
            "post_office_count": len(offices),
            "post_offices": offices,
            "message": f"{len(offices)} locality match(es) returned via fallback PIN directory.",
            "disclaimer": POSTAL_PIN_DISCLAIMER,
        }

    return {
        "ok": False,
        "valid": True,
        "pin_code": pin,
        "error": f"PIN directory service unavailable ({res.get('error')}).",
        "post_offices": [],
        "disclaimer": POSTAL_PIN_DISCLAIMER,
    }

