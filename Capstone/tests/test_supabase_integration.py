"""
Supabase Configuration & Integration Tests
Verifies public configuration exposure, security boundaries (no secret keys exposed),
and template context injection.
"""
from app.services.supabase_service import is_supabase_configured, get_supabase_public_config


def test_supabase_config_helpers(app):
    """Test Supabase configuration helper behavior with and without config."""
    with app.app_context():
        # Initially url is empty
        cfg = get_supabase_public_config(app)
        assert "enabled" in cfg
        assert "publishable_key" in cfg
        assert "service_role" not in cfg
        assert "secret_key" not in cfg

        # Mock configured state
        app.config["SUPABASE_URL"] = "https://xyzexample.supabase.co"
        app.config["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_-EZ9bdSoqDr7zRyX0Zze3w_BaTAepOS"

        assert is_supabase_configured(app) is True
        active_cfg = get_supabase_public_config(app)
        assert active_cfg["enabled"] is True
        assert active_cfg["url"] == "https://xyzexample.supabase.co"
        assert active_cfg["publishable_key"] == "sb_publishable_-EZ9bdSoqDr7zRyX0Zze3w_BaTAepOS"


def test_api_supabase_config_endpoint(client, app):
    """GET /api/supabase/config returns sanitized JSON configuration without secret leaks."""
    app.config["SUPABASE_URL"] = "https://xyzexample.supabase.co"
    app.config["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_-EZ9bdSoqDr7zRyX0Zze3w_BaTAepOS"

    resp = client.get("/api/supabase/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["publishable_key"] == "sb_publishable_-EZ9bdSoqDr7zRyX0Zze3w_BaTAepOS"
    assert data["data"]["url"] == "https://xyzexample.supabase.co"
    # Ensure sensitive terms are never in output
    raw_text = resp.data.decode("utf-8").lower()
    assert "service_role" not in raw_text
    assert "sb_secret" not in raw_text
