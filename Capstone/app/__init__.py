"""
Flask Application Factory
EV Charging Station Management System - Production Hardened
"""
import os
import secrets
from datetime import timedelta
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

load_dotenv()

csrf = CSRFProtect()
oauth = OAuth()


def is_google_oauth_configured(target_app=None):
    """Return True only when real Google OAuth client credentials are configured."""
    cfg = target_app.config if target_app else None
    client_id = (cfg.get("GOOGLE_CLIENT_ID") if cfg else os.getenv("GOOGLE_CLIENT_ID", "")).strip()
    client_secret = (cfg.get("GOOGLE_CLIENT_SECRET") if cfg else os.getenv("GOOGLE_CLIENT_SECRET", "")).strip()
    return bool(client_id and client_secret)


def ensure_google_oauth_client(target_app):
    """Register or refresh the Authlib Google OIDC client when credentials are present."""
    if not is_google_oauth_configured(target_app):
        return None
    desired_id = target_app.config["GOOGLE_CLIENT_ID"]
    desired_secret = target_app.config["GOOGLE_CLIENT_SECRET"]
    client = oauth.create_client("google")
    if client is None or getattr(client, "client_id", None) != desired_id:
        oauth.register(
            name="google",
            overwrite=True,
            client_id=desired_id,
            client_secret=desired_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        client = oauth.create_client("google")
    return client


def _is_production(app=None):
    """Determine if running in production mode (Vercel or FLASK_ENV=production)."""
    if app and app.config.get("TESTING"):
        return False
    flask_env = os.getenv("FLASK_ENV", "development").strip().lower()
    vercel = os.getenv("VERCEL", "").strip()
    return flask_env == "production" or vercel == "1"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    is_testing = bool(test_config and test_config.get("TESTING"))
    is_prod = False if is_testing else _is_production()

    secret_key = (
        (test_config.get("SECRET_KEY") if test_config else None)
        or os.getenv("SECRET_KEY", "").strip()
    )
    if not secret_key:
        if is_prod:
            raise RuntimeError("SECRET_KEY environment variable is required in production.")
        # Ephemeral per-process fallback for local dev/test only (never a static hardcoded secret)
        secret_key = secrets.token_hex(32)

    # Configuration
    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DEBUG=False if is_prod else (os.getenv("FLASK_DEBUG", "False").strip().lower() in ("true", "1", "yes")),
        MYSQL_HOST=os.getenv("MYSQL_HOST", "127.0.0.1"),
        MYSQL_PORT=int(os.getenv("MYSQL_PORT", 3306)),
        MYSQL_USER=os.getenv("MYSQL_USER", "root"),
        MYSQL_PASSWORD=os.getenv("MYSQL_PASSWORD", ""),
        MYSQL_DATABASE=os.getenv("MYSQL_DATABASE", "ev_charging_db"),
        DATABASE_URL=os.getenv("DATABASE_URL", "").strip(),
        MYSQL_SSL_CA=os.getenv("MYSQL_SSL_CA", "").strip(),
        SUPABASE_URL=os.getenv("SUPABASE_URL", "").strip(),
        SUPABASE_PUBLISHABLE_KEY=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        WEB3FORMS_ACCESS_KEY=os.getenv("WEB3FORMS_ACCESS_KEY", "").strip(),
        RAZORPAY_KEY_ID=os.getenv("RAZORPAY_KEY_ID", "").strip(),
        RAZORPAY_KEY_SECRET=os.getenv("RAZORPAY_KEY_SECRET", "").strip(),
        RAZORPAY_WEBHOOK_SECRET=os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip(),
        GOOGLE_MAPS_API_KEY=os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
        GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        GOOGLE_REDIRECT_URI=os.getenv("GOOGLE_REDIRECT_URI", "").strip(),
        OPEN_CHARGE_MAP_API_KEY=os.getenv("OPEN_CHARGE_MAP_API_KEY", "").strip(),
        NOMINATIM_USER_AGENT=os.getenv("NOMINATIM_USER_AGENT", "EZChargeNetworkPortal/1.0 (academic-ev-demo)").strip(),
        OPEN_METEO_BASE_URL=os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast").strip(),
        OSRM_BASE_URL=os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").strip(),
        POSTAL_PIN_API_URL=os.getenv("POSTAL_PIN_API_URL", "https://api.postalpincode.in/pincode").strip(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_prod,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=3600,
        SEND_FILE_MAX_AGE_DEFAULT=86400,
    )

    if test_config:
        app.config.update(test_config)

    if is_prod:
        app.config["DEBUG"] = False

    if is_prod:
        has_db_url = bool(app.config.get("DATABASE_URL"))
        has_mysql_creds = all([
            app.config.get("MYSQL_HOST"),
            app.config.get("MYSQL_USER"),
            app.config.get("MYSQL_PASSWORD"),
            app.config.get("MYSQL_DATABASE"),
        ])
        if not (has_db_url or has_mysql_creds):
            app.logger.warning(
                "Production database configuration (DATABASE_URL or MYSQL_*) is missing. "
                "The portal will serve static & reference pages; set DATABASE_URL in Vercel for live database features."
            )

    csrf.init_app(app)
    oauth.init_app(app)
    ensure_google_oauth_client(app)

    # Prevent browser bfcache from caching sensitive auth/CSRF forms
    @app.after_request
    def _set_auth_cache_headers(response):
        p = request.path or ""
        if p in ("/login", "/register", "/forgot-password", "/auth/csrf-token") or p.startswith("/reset-password"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Register Blueprints
    from app.routes.public import public_bp
    from app.routes.auth import auth_bp
    from app.routes.customer import customer_bp
    from app.routes.admin import admin_bp
    from app.routes.owner import owner_bp
    from app.routes.api import api_bp
    from app.services.platform_service import get_platform_operator, get_verified_social_links

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp, url_prefix="/customer")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(owner_bp, url_prefix="/owner")
    app.register_blueprint(api_bp, url_prefix="/api")

    from app.services.supabase_service import get_supabase_public_config

    @app.context_processor
    def inject_platform_identity():
        return {
            "platform_operator": get_platform_operator(),
            "social_links": get_verified_social_links(),
            "google_maps_api_key": app.config.get("GOOGLE_MAPS_API_KEY", ""),
            "google_oauth_enabled": is_google_oauth_configured(app),
            "supabase_config": get_supabase_public_config(app),
        }

    @app.after_request
    def add_cache_and_performance_headers(response):
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
        return response

    # Global Error Handlers
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({
                "success": False,
                "error": "Your security token expired. Please refresh and try again.",
                "csrf_expired": True,
            }), 400
        # Determine safe same-origin retry URL
        retry_url = request.path or "/"
        if request.referrer:
            parsed = urlparse(request.referrer)
            if not parsed.netloc or parsed.netloc == request.host:
                retry_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        return render_template(
            "error.html",
            code=400,
            csrf_error=True,
            retry_url=retry_url or "/",
            message="Security check expired (invalid or stale CSRF token). This commonly happens after using browser Back/Forward or when a session times out.",
        ), 400

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Requested resource not found."}), 404
        return render_template("error.html", code=404, message="Requested page not found."), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Access Denied."}), 403
        return render_template("error.html", code=403, message="Access Denied: You do not have permission to access this resource."), 403

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "An internal server error occurred."}), 500
        return render_template("error.html", code=500, message="An internal database or server error occurred."), 500

    return app
