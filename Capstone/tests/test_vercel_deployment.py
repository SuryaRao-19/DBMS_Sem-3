"""
Phase 5 Verification Tests — Vercel Serverless Compatibility & Routing
Verifies api/index.py WSGI entrypoint, vercel.json configuration,
static asset serving, health check endpoint, and HTML routes through Vercel's app object.
"""
import json
import os
import importlib


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_vercel_json_is_valid_and_rewrites_to_api_index():
    """vercel.json parses cleanly and routes incoming paths to /api/index without legacy builds."""
    vercel_path = os.path.join(ROOT_DIR, "vercel.json")
    assert os.path.exists(vercel_path)
    with open(vercel_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    assert "builds" not in cfg
    assert cfg.get("functions", {}).get("api/index.py", {}).get("maxDuration", 0) >= 10
    rewrites = cfg.get("rewrites", [])
    assert any(r.get("destination", "").startswith("/api/index") for r in rewrites)


def test_vercel_entrypoint_exports_flask_app_and_serves_routes():
    """api.index exposes Flask app and serves landing, contact, health, and static assets."""
    mod = importlib.import_module("api.index")
    assert hasattr(mod, "app")
    vercel_app = mod.app
    vercel_app.config["TESTING"] = True

    with vercel_app.test_client() as c:
        home = c.get("/")
        assert home.status_code == 200
        assert b"EV ChargeNet" in home.data

        stations = c.get("/stations")
        assert stations.status_code == 200

        contact = c.get("/contact")
        assert contact.status_code == 200

        health = c.get("/api/health")
        assert health.status_code == 200
        payload = health.get_json()
        assert payload["status"] == "HEALTHY"
        assert payload["database_connected"] is True

        css = c.get("/static/css/style.css")
        assert css.status_code == 200

        js = c.get("/static/js/main.js")
        assert js.status_code == 200
