"""
Authentication Routes (Local Auth, Google OAuth 2.0 / OIDC, Forgot/Reset Password & CSRF Refresh)
EV Charging Station Management System - Production Hardened
"""
import secrets
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_wtf.csrf import generate_csrf
from app import oauth, is_google_oauth_configured, ensure_google_oauth_client
from app.routes.auth_middleware import login_required, get_current_user_id, normalize_role
from app.services.auth_service import (
    authenticate_user,
    register_user,
    authenticate_or_register_google_user,
    link_google_account_to_user,
    create_password_reset_token,
    verify_password_reset_token,
    reset_password_with_token,
    check_auth_rate_limit,
    save_uploaded_avatar,
)

auth_bp = Blueprint("auth", __name__)


def _redirect_for_role(role):
    norm = normalize_role(role)
    if norm == "ADMIN":
        return redirect(url_for("admin.dashboard"))
    if norm == "OWNER":
        return redirect(url_for("owner.dashboard"))
    return redirect(url_for("customer.dashboard"))


def _safe_next_url(next_url):
    """Only allow same-origin relative redirects for post-login navigation."""
    if not next_url:
        return None
    parsed = urlparse(next_url.strip())
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return None
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _establish_authenticated_session(user, remember_me=True):
    """Regenerate session cleanly after authentication to prevent session fixation."""
    session.clear()
    session.permanent = bool(remember_me)
    session["user_id"] = user["user_id"]
    session["full_name"] = user["full_name"]
    session["email"] = user["email"]
    session["role"] = normalize_role(user.get("role"))
    session["auth_provider"] = user.get("auth_provider", "LOCAL")
    if user.get("profile_picture_url"):
        session["profile_picture_url"] = user["profile_picture_url"]


@auth_bp.route("/auth/csrf-token", methods=["GET"])
def refresh_csrf_token():
    """Return a fresh CSRF token synced with the active session (used after bfcache restore)."""
    return jsonify({"csrf_token": generate_csrf()}), 200


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return _redirect_for_role(session.get("role"))

    next_target = _safe_next_url(request.args.get("next") or request.form.get("next"))

    if request.method == "POST":
        max_attempts = int(current_app.config.get("AUTH_RATE_LIMIT_MAX", 20))
        allowed, retry_after = check_auth_rate_limit(
            "login", request.remote_addr or "local", max_attempts=max_attempts
        )
        if not allowed:
            flash(f"Too many sign-in attempts. Please wait {retry_after} seconds before trying again.", "danger")
            return render_template("login.html", email=request.form.get("email", ""), next_url=next_target or ""), 429

        email = request.form.get("email", "")
        password = request.form.get("password", "")
        remember_me = request.form.get("remember_me") in ("1", "true", "on", "yes")

        user, err = authenticate_user(email, password)
        if err:
            flash(err, "danger")
            return render_template("login.html", email=email, next_url=next_target or "")

        _establish_authenticated_session(user, remember_me=remember_me)
        flash(f"Welcome back, {user['full_name']}!", "success")
        if next_target:
            return redirect(next_target)
        return _redirect_for_role(user["role"])

    return render_template("login.html", next_url=next_target or "")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return _redirect_for_role(session.get("role"))

    if request.method == "POST":
        max_attempts = int(current_app.config.get("AUTH_RATE_LIMIT_MAX", 20))
        allowed, retry_after = check_auth_rate_limit(
            "register", request.remote_addr or "local", max_attempts=max_attempts
        )
        if not allowed:
            flash(f"Too many registration attempts. Please wait {retry_after} seconds and try again.", "danger")
            return render_template("register.html"), 429

        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Reject any client attempt to submit an unauthorized role (e.g., ADMIN or OWNER)
        submitted_role = request.form.get("role", "").strip().upper()
        if submitted_role and submitted_role not in ("CUSTOMER", "USER"):
            flash(
                "Public registration creates EV Customer accounts only. Station Owners must apply via the Partner Application.",
                "danger",
            )
            return render_template("register.html", full_name=full_name, email=email, phone=phone), 403

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", full_name=full_name, email=email, phone=phone)

        avatar_url = None
        upload = request.files.get("profile_picture")
        if upload and upload.filename:
            avatar_url, upload_err = save_uploaded_avatar(upload, current_app.static_folder)
            if upload_err:
                flash(upload_err, "danger")
                return render_template("register.html", full_name=full_name, email=email, phone=phone)
        else:
            raw_pic_url = (request.form.get("profile_picture_url") or "").strip()
            if raw_pic_url:
                parsed_pic = urlparse(raw_pic_url)
                if parsed_pic.scheme in ("https", "http") and parsed_pic.netloc:
                    avatar_url = raw_pic_url[:500]
                else:
                    flash("Profile picture URL must start with https:// or http://.", "danger")
                    return render_template("register.html", full_name=full_name, email=email, phone=phone)

        uid, err = register_user(
            full_name,
            email,
            phone,
            password,
            role="CUSTOMER",
            allow_admin=False,
            allow_owner=False,
            profile_picture_url=avatar_url,
        )
        if err:
            flash(err, "danger")
            return render_template("register.html", full_name=full_name, email=email, phone=phone)

        flash("Your EV ChargeNet Customer account is ready! Please sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/auth/google", methods=["GET"])
@auth_bp.route("/auth/google/login", methods=["GET"])
def google_login():
    """Initiate Google OAuth 2.0 / OpenID Connect Authorization Code flow."""
    if "user_id" in session:
        return _redirect_for_role(session.get("role"))

    if not is_google_oauth_configured(current_app):
        flash(
            "Google Sign-In is not configured yet in this environment. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET or sign in using email and password.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    google_client = ensure_google_oauth_client(current_app)
    if not google_client:
        flash("Unable to initialize Google OAuth client. Please check configuration.", "danger")
        return redirect(url_for("auth.login"))

    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for("auth.google_callback", _external=True)
    nonce = secrets.token_urlsafe(32)
    session["google_oauth_nonce"] = nonce
    session["google_oauth_action"] = "login"
    return google_client.authorize_redirect(redirect_uri, nonce=nonce)


@auth_bp.route("/auth/google/link", methods=["GET"])
@login_required
def google_link():
    """Allow an authenticated local user to explicitly link their Google account from Profile."""
    if not is_google_oauth_configured(current_app):
        flash("Google OAuth is not configured yet in this environment.", "warning")
        return redirect(url_for("public.profile"))

    google_client = ensure_google_oauth_client(current_app)
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for("auth.google_callback", _external=True)
    nonce = secrets.token_urlsafe(32)
    session["google_oauth_nonce"] = nonce
    session["google_oauth_action"] = "link"
    return google_client.authorize_redirect(redirect_uri, nonce=nonce)


@auth_bp.route("/auth/google/callback", methods=["GET"])
def google_callback():
    """Handle Google OIDC callback, validate state/nonce/ID-token, and establish session safely."""
    oauth_error = request.args.get("error")
    if oauth_error:
        flash(f"Google Sign-In was cancelled or declined ({oauth_error}).", "warning")
        return redirect(url_for("auth.login"))

    if not is_google_oauth_configured(current_app):
        flash("Google OAuth is not configured in this environment.", "warning")
        return redirect(url_for("auth.login"))

    google_client = ensure_google_oauth_client(current_app)
    if not google_client:
        flash("Google OAuth client unavailable.", "danger")
        return redirect(url_for("auth.login"))

    expected_nonce = session.pop("google_oauth_nonce", None)
    oauth_action = session.pop("google_oauth_action", "login")

    try:
        token = google_client.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = google_client.parse_id_token(token, nonce=expected_nonce)
        if not userinfo:
            userinfo = google_client.userinfo()
    except Exception:
        flash("Google authentication verification failed (invalid or expired OAuth state). Please try again.", "danger")
        return redirect(url_for("public.profile") if oauth_action == "link" else url_for("auth.login"))

    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    email_verified = bool(userinfo.get("email_verified") is True)
    full_name = userinfo.get("name") or email
    picture_url = userinfo.get("picture")

    if oauth_action == "link" and "user_id" in session:
        ok, err = link_google_account_to_user(
            user_id=get_current_user_id(),
            google_sub=google_sub,
            email=email,
            picture_url=picture_url,
            email_verified=email_verified,
            ip_address=request.remote_addr,
        )
        if not ok:
            flash(err, "danger")
        else:
            session["auth_provider"] = "HYBRID"
            if picture_url:
                session["profile_picture_url"] = picture_url
            flash("Google account verified and linked successfully!", "success")
        return redirect(url_for("public.profile"))

    user, err = authenticate_or_register_google_user(
        google_sub=google_sub,
        email=email,
        full_name=full_name,
        picture_url=picture_url,
        email_verified=email_verified,
        ip_address=request.remote_addr,
    )
    if err:
        flash(err, "danger")
        return redirect(url_for("auth.login"))

    _establish_authenticated_session(user)
    flash(f"Signed in with Google as {user['full_name']}.", "success")
    return _redirect_for_role(user["role"])


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Request a timed password reset token without leaking account existence."""
    if "user_id" in session:
        return _redirect_for_role(session.get("role"))

    submitted = False
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your registered email address.", "danger")
            return render_template("forgot_password.html", email=email, submitted=False)

        raw_token = create_password_reset_token(email, ip_address=request.remote_addr)
        # Never expose reset URLs in HTTP responses or logs in production;
        # only log local dev reset path to server stderr/stdout when DEBUG is explicitly True.
        if raw_token and current_app.config.get("DEBUG") and not current_app.config.get("TESTING"):
            current_app.logger.info("Local dev password reset URL requested for %s: /reset-password/%s", email, raw_token)

        submitted = True
        flash(
            "If an active account matches that email, a password reset link has been generated (valid for 30 minutes). If your account uses Google Sign-In, you can also continue directly with Google.",
            "info",
        )
        return render_template("forgot_password.html", email=email, submitted=submitted)

    return render_template("forgot_password.html", submitted=submitted)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Consume a valid single-use reset token to set a new password."""
    token_row = verify_password_reset_token(token)
    if not token_row:
        flash("This password reset link is invalid or has expired. Please request a new one.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", token=token, email=token_row["email"])

        ok, err = reset_password_with_token(token, password, ip_address=request.remote_addr)
        if not ok:
            flash(err, "danger")
            return render_template("reset_password.html", token=token, email=token_row["email"])

        flash("Your password has been updated. You can now sign in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token, email=token_row["email"])


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out securely.", "info")
    return redirect(url_for("auth.login"))
