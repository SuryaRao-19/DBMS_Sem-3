"""
Supabase Integration Service
EV ChargeNet — Managed Database & Client Tier Helper

Provides safe handling of Supabase public client configuration.
Row-Level Security (RLS) and server-side RBAC remain strictly enforced by Flask.
Never expose service_role or backend secret keys to client JS.
"""
import os
from flask import current_app


def is_supabase_configured(app=None):
    """Check whether Supabase public credentials are provided."""
    target = app or (current_app._get_current_object() if current_app else None)
    if target:
        url = target.config.get("SUPABASE_URL", "")
        key = target.config.get("SUPABASE_PUBLISHABLE_KEY", "")
    else:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")

    return bool(url and key and key.strip())


def get_supabase_public_config(app=None):
    """
    Return sanitized public client configuration safe for frontend templates.
    Only the project URL and publishable key are returned; secret keys are never included.
    """
    target = app or (current_app._get_current_object() if current_app else None)
    if target:
        url = target.config.get("SUPABASE_URL", "").strip()
        pub_key = target.config.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    else:
        url = os.getenv("SUPABASE_URL", "").strip()
        pub_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()

    return {
        "enabled": bool(url and pub_key),
        "url": url,
        "publishable_key": pub_key,
    }
