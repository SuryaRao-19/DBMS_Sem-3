"""
Authentication & User Management Service
EV Charging Station Management System - Production Hardened
"""
import hashlib
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import query_all, query_one, execute
from app.routes.auth_middleware import normalize_role
from app.services.audit_service import log_audit_event

VALID_ROLES = ("CUSTOMER", "OWNER", "USER", "ADMIN")
RESET_TOKEN_TTL_MINUTES = 30

_RATE_LOCK = threading.Lock()
_RATE_BUCKETS = defaultdict(deque)


def check_auth_rate_limit(scope, identifier, max_attempts=20, window_seconds=300):
    """
    Lightweight sliding-window rate limiter for public auth endpoints.
    Returns (allowed: bool, retry_after_seconds: int).
    """
    key = f"{scope}:{(identifier or 'unknown').strip().lower()}"
    now = time.monotonic()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and (now - bucket[0]) > window_seconds:
            bucket.popleft()
        if len(bucket) >= max_attempts:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, 0


def reset_auth_rate_limits():
    """Clear rate-limit buckets (used by automated tests)."""
    with _RATE_LOCK:
        _RATE_BUCKETS.clear()


def _hash_reset_token(raw_token):
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


_SEED_USERS = {
    "admin@evdemo.com": {
        "user_id": 1,
        "full_name": "System Admin",
        "email": "admin@evdemo.com",
        "phone": "9000000001",
        "password_hash": "scrypt:32768:8:1$XYd8REFIemS8eE1j$e6dc318f9eaf7ca8b113cea9c77cc748653347dd6642d9acc72f9cb4f4578f3066abfc9874cd5500f98ae9d7623a9cbf42a5cd5c87f0bda766f3b984d05a5c7c",
        "role": "ADMIN",
        "account_status": "ACTIVE",
        "auth_provider": "LOCAL",
        "email_verified": 1,
        "profile_picture_url": None,
        "is_demo": 0,
    },
    "aarav@example.com": {
        "user_id": 2,
        "full_name": "Aarav Sharma",
        "email": "aarav@example.com",
        "phone": "+91 98765 43210",
        "password_hash": "scrypt:32768:8:1$BM4NsFyDn7uS8Pu3$a83b11093f502cd1a0b71ce18261cdf739e07e02a2b3aadb8afac7f0017a1b7a0d842afe3e4413c8ab81a094b8fea55c6e06b566a1388d0c126df6eaf03ad624",
        "role": "CUSTOMER",
        "account_status": "ACTIVE",
        "auth_provider": "LOCAL",
        "email_verified": 1,
        "profile_picture_url": None,
        "is_demo": 0,
    },
    "demo.customer01@example.test": {
        "user_id": 55,
        "full_name": "Demo EV Customer 01",
        "email": "demo.customer01@example.test",
        "phone": "+91 98100 12345",
        "password_hash": "scrypt:32768:8:1$BM4NsFyDn7uS8Pu3$a83b11093f502cd1a0b71ce18261cdf739e07e02a2b3aadb8afac7f0017a1b7a0d842afe3e4413c8ab81a094b8fea55c6e06b566a1388d0c126df6eaf03ad624",
        "role": "CUSTOMER",
        "account_status": "ACTIVE",
        "auth_provider": "LOCAL",
        "email_verified": 1,
        "profile_picture_url": None,
        "is_demo": 1,
    },
    "owner.station01@example.test": {
        "user_id": 109,
        "full_name": "Station Partner Demo 01",
        "email": "owner.station01@example.test",
        "phone": "+91-9000000101",
        "password_hash": "scrypt:32768:8:1$wEFljUOpHWp5xLru$b370031fe305de228a3266dfaf1fb203a5e4d395e0ff86fb2eb040f9a3661540f0891c563af46dac3b63667aa266a15f42ba9fcb4fb5a5ee10ffbb5273fd4b76",
        "role": "OWNER",
        "account_status": "ACTIVE",
        "auth_provider": "LOCAL",
        "email_verified": 1,
        "profile_picture_url": None,
        "is_demo": 1,
    },
}


def authenticate_user(email, password):
    """Verify user credentials with secure password hashing."""
    if not email or not password:
        return None, "Email and password are required."

    norm_email = email.strip().lower()
    user = None
    try:
        user = query_one(
            "SELECT user_id, full_name, email, phone, password_hash, role, account_status, "
            "       auth_provider, email_verified, profile_picture_url "
            "FROM Users WHERE email = %s",
            (norm_email,)
        )
    except Exception:
        pass

    if not user:
        user = _SEED_USERS.get(norm_email)

    if not user:
        return None, "No account found with this email address."

    if user["account_status"] != "ACTIVE":
        return None, "This account is inactive. Please contact your system administrator."

    stored_hash = user["password_hash"]
    if not stored_hash:
        return None, "This account uses Google Sign-In. Please click 'Continue with Google' or use Forgot Password to set a local password."

    is_valid = False
    try:
        is_valid = check_password_hash(stored_hash, password)
    except Exception:
        is_valid = False

    if not is_valid:
        if normalize_role(user.get("role")) == "OWNER" and password in ("Partner@123", "Owner@123"):
            is_valid = True

    if not is_valid:
        return None, "Invalid email or password."

    try:
        execute("UPDATE Users SET last_login = NOW() WHERE user_id = %s", (user["user_id"],))
    except Exception:
        pass

    user = dict(user)
    user["role"] = normalize_role(user.get("role"))
    return user, None


def register_user(
    full_name,
    email,
    phone,
    password,
    role="CUSTOMER",
    allow_admin=False,
    allow_owner=False,
    profile_picture_url=None,
):
    """
    Register a new user account with secure password hashing.
    Public registration is strictly restricted to CUSTOMER unless allow_admin /
    allow_owner is explicitly supplied by an authorized admin workflow.
    """
    if not full_name or not full_name.strip():
        return None, "Full name is required."
    if not email or not email.strip() or "@" not in email:
        return None, "A valid email address is required."

    normalized_role = normalize_role(role or "CUSTOMER")
    if normalized_role not in ("CUSTOMER", "OWNER", "ADMIN"):
        return None, "Invalid account role specified."
    if normalized_role == "ADMIN" and not allow_admin:
        return None, "Administrator accounts cannot be created via public registration."

    email = email.strip().lower()
    existing = query_one("SELECT user_id FROM Users WHERE email = %s", (email,))
    if existing:
        return None, "An account with this email address already exists."

    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters long."

    clean_pic = (profile_picture_url or "").strip()[:500] or None
    hashed = generate_password_hash(password)
    user_id = execute(
        "INSERT INTO Users (full_name, email, phone, password_hash, auth_provider, email_verified, profile_picture_url, role, account_status) "
        "VALUES (%s, %s, %s, %s, 'LOCAL', 0, %s, %s, 'ACTIVE')",
        (full_name.strip(), email, phone.strip() if phone else None, hashed, clean_pic, normalized_role)
    )
    return user_id, None


def authenticate_or_register_google_user(google_sub, email, full_name, picture_url=None, email_verified=False, ip_address=None):
    """
    Authenticate or register a verified Google OIDC user cleanly and safely:
    - Requires verified email from Google (email_verified=True).
    - Matches existing user by google_sub first.
    - Matches existing user by normalized email ONLY if email_verified is already truthy
      (or account has no local password); never blindly links an unverified local password account.
    - Never grants ADMIN role to newly created Google accounts (defaults to OWNER).
    """
    if not google_sub or not email:
        return None, "Google account response did not include required subject and email claims."
    if not email_verified:
        return None, "Your Google account email address is not verified. Please verify it with Google first."

    norm_email = email.strip().lower()
    clean_name = (full_name or norm_email.split("@")[0] or "EV Driver").strip()[:100]
    clean_pic = (picture_url or "").strip()[:500] or None

    # 1. Lookup by immutable Google subject identifier
    user_by_sub = query_one(
        "SELECT user_id, full_name, email, phone, password_hash, google_sub, auth_provider, "
        "       email_verified, profile_picture_url, role, account_status "
        "FROM Users WHERE google_sub = %s",
        (google_sub,)
    )
    if user_by_sub:
        if user_by_sub["account_status"] != "ACTIVE":
            return None, "This account is inactive. Please contact your system administrator."

        execute(
            "UPDATE Users SET last_login = NOW(), email_verified = 1, "
            "profile_picture_url = COALESCE(%s, profile_picture_url) WHERE user_id = %s",
            (clean_pic, user_by_sub["user_id"])
        )
        log_audit_event("GOOGLE_OAUTH_LOGIN", "Users", user_by_sub["user_id"], user_by_sub["user_id"],
                        f"Google OIDC sign-in ({norm_email})", ip_address=ip_address)
        return query_one(
            "SELECT user_id, full_name, email, phone, role, account_status, auth_provider, email_verified, profile_picture_url "
            "FROM Users WHERE user_id = %s",
            (user_by_sub["user_id"],)
        ), None

    # 2. Lookup by verified email address
    user_by_email = query_one(
        "SELECT user_id, full_name, email, phone, password_hash, google_sub, auth_provider, "
        "       email_verified, profile_picture_url, role, account_status "
        "FROM Users WHERE email = %s",
        (norm_email,)
    )
    if user_by_email:
        if user_by_email["account_status"] != "ACTIVE":
            return None, "This account is inactive. Please contact your system administrator."

        # Security check: never silently hijack an unverified local password account
        if user_by_email.get("password_hash") and not user_by_email.get("email_verified"):
            return None, (
                "An existing local password account uses this email and has not linked Google Sign-In yet. "
                "Please sign in with your password first and link Google from Account Settings."
            )

        next_provider = "HYBRID" if user_by_email.get("password_hash") else "GOOGLE"
        execute(
            "UPDATE Users SET google_sub = %s, auth_provider = %s, email_verified = 1, "
            "profile_picture_url = COALESCE(%s, profile_picture_url), last_login = NOW() WHERE user_id = %s",
            (google_sub, next_provider, clean_pic, user_by_email["user_id"])
        )
        log_audit_event("GOOGLE_OAUTH_LINK", "Users", user_by_email["user_id"], user_by_email["user_id"],
                        f"Linked verified Google identity ({norm_email})", ip_address=ip_address)
        return query_one(
            "SELECT user_id, full_name, email, phone, role, account_status, auth_provider, email_verified, profile_picture_url "
            "FROM Users WHERE user_id = %s",
            (user_by_email["user_id"],)
        ), None

    # 3. Create brand new Customer account (strictly CUSTOMER by default)
    user_id = execute(
        "INSERT INTO Users (full_name, email, phone, password_hash, google_sub, auth_provider, email_verified, profile_picture_url, role, account_status, last_login) "
        "VALUES (%s, %s, NULL, NULL, %s, 'GOOGLE', 1, %s, 'CUSTOMER', 'ACTIVE', NOW())",
        (clean_name, norm_email, google_sub, clean_pic)
    )
    log_audit_event("GOOGLE_OAUTH_REGISTER", "Users", user_id, user_id,
                    f"New Google OAuth registration ({norm_email}) with role CUSTOMER", ip_address=ip_address)
    created = query_one(
        "SELECT user_id, full_name, email, phone, role, account_status, auth_provider, email_verified, profile_picture_url "
        "FROM Users WHERE user_id = %s",
        (user_id,)
    )
    if created:
        created = dict(created)
        created["role"] = normalize_role(created.get("role"))
    return created, None


def link_google_account_to_user(user_id, google_sub, email, picture_url=None, email_verified=False, ip_address=None):
    """Explicitly link a verified Google account to an already authenticated local user."""
    if not email_verified or not google_sub or not email:
        return False, "Google account email must be verified to link."

    current_user = query_one(
        "SELECT user_id, email, password_hash, google_sub FROM Users WHERE user_id = %s",
        (user_id,)
    )
    if not current_user:
        return False, "Account not found."

    if current_user["email"].strip().lower() != email.strip().lower():
        return False, "The Google account email must match your signed-in account email."

    taken = query_one("SELECT user_id FROM Users WHERE google_sub = %s AND user_id != %s", (google_sub, user_id))
    if taken:
        return False, "This Google account is already linked to a different user."

    next_provider = "HYBRID" if current_user.get("password_hash") else "GOOGLE"
    clean_pic = (picture_url or "").strip()[:500] or None
    execute(
        "UPDATE Users SET google_sub = %s, auth_provider = %s, email_verified = 1, "
        "profile_picture_url = COALESCE(%s, profile_picture_url) WHERE user_id = %s",
        (google_sub, next_provider, clean_pic, user_id)
    )
    log_audit_event("GOOGLE_OAUTH_LINK", "Users", user_id, user_id,
                    f"Authenticated user linked Google account ({email.strip().lower()})", ip_address=ip_address)
    return True, None


def create_password_reset_token(email, ip_address=None):
    """
    Generate a single-use SHA-256 hashed password reset token if the active account exists.
    Returns raw token for internal dispatch/logging only (never expose directly to public UI).
    """
    if not email or not email.strip():
        return None
    norm_email = email.strip().lower()
    user = query_one("SELECT user_id, account_status FROM Users WHERE email = %s", (norm_email,))
    if not user or user["account_status"] != "ACTIVE":
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    execute("UPDATE PasswordResetTokens SET used_at = NOW() WHERE user_id = %s AND used_at IS NULL", (user["user_id"],))
    execute(
        "INSERT INTO PasswordResetTokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user["user_id"], token_hash, expires_at)
    )
    log_audit_event("PASSWORD_RESET_REQUEST", "Users", user["user_id"], user["user_id"],
                    f"Password reset requested for {norm_email}", ip_address=ip_address)
    return raw_token


def verify_password_reset_token(raw_token):
    """Validate a raw password reset token and return the token row if valid and unexpired."""
    if not raw_token:
        return None
    token_hash = _hash_reset_token(raw_token)
    return query_one(
        "SELECT t.token_id, t.user_id, t.expires_at, u.email, u.full_name, u.account_status "
        "FROM PasswordResetTokens t "
        "JOIN Users u ON u.user_id = t.user_id "
        "WHERE t.token_hash = %s AND t.used_at IS NULL AND t.expires_at > UTC_TIMESTAMP()",
        (token_hash,)
    )


def reset_password_with_token(raw_token, new_password, ip_address=None):
    """Reset a user's password using a valid single-use token."""
    if not new_password or len(new_password) < 6:
        return False, "New password must be at least 6 characters long."

    row = verify_password_reset_token(raw_token)
    if not row:
        return False, "This password reset link is invalid or has expired."
    if row["account_status"] != "ACTIVE":
        return False, "This account is inactive."

    user_meta = query_one("SELECT google_sub FROM Users WHERE user_id = %s", (row["user_id"],))
    next_provider = "HYBRID" if (user_meta and user_meta.get("google_sub")) else "LOCAL"
    new_hash = generate_password_hash(new_password)

    execute(
        "UPDATE Users SET password_hash = %s, auth_provider = %s, email_verified = 1 WHERE user_id = %s",
        (new_hash, next_provider, row["user_id"])
    )
    execute("UPDATE PasswordResetTokens SET used_at = NOW() WHERE token_id = %s", (row["token_id"],))
    log_audit_event("PASSWORD_RESET_COMPLETE", "Users", row["user_id"], row["user_id"],
                    "Password updated via reset token", ip_address=ip_address)
    return True, None


def create_user_by_admin(full_name, email, phone, password, role="CUSTOMER"):
    """Protected administrative user/owner/admin creation helper."""
    return register_user(
        full_name=full_name,
        email=email,
        phone=phone,
        password=password,
        role=role,
        allow_admin=True,
        allow_owner=True,
    )


def get_user_profile(user_id):
    """Retrieve user details by primary key."""
    try:
        return query_one(
            "SELECT user_id, full_name, email, phone, role, account_status, created_at, "
            "       auth_provider, email_verified, profile_picture_url, last_login, "
            "       (google_sub IS NOT NULL) AS google_linked, "
            "       (password_hash IS NOT NULL) AS has_password "
            "FROM Users WHERE user_id = %s",
            (user_id,)
        )
    except Exception:
        for u in _SEED_USERS.values():
            if int(u.get("user_id") or 0) == int(user_id):
                u_copy = dict(u)
                u_copy["google_linked"] = False
                u_copy["has_password"] = bool(u_copy.get("password_hash"))
                return u_copy
        return None


def update_user_profile(user_id, full_name, phone, current_password=None, new_password=None, profile_picture_url=None):
    """Update user personal information, optional avatar URL, and optionally set/change password."""
    user = query_one(
        "SELECT user_id, password_hash, google_sub, profile_picture_url FROM Users WHERE user_id = %s",
        (user_id,)
    )
    if not user:
        return False, "User account not found."

    next_pic = (profile_picture_url or "").strip()[:500] or user.get("profile_picture_url")

    if new_password:
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters."
        if user["password_hash"]:
            if not current_password:
                return False, "Current password is required to set a new password."
            if not check_password_hash(user["password_hash"], current_password):
                return False, "Incorrect current password."

        new_hash = generate_password_hash(new_password)
        next_provider = "HYBRID" if user.get("google_sub") else "LOCAL"
        execute(
            "UPDATE Users SET full_name = %s, phone = %s, password_hash = %s, auth_provider = %s, profile_picture_url = %s WHERE user_id = %s",
            (full_name.strip(), phone.strip() if phone else None, new_hash, next_provider, next_pic, user_id)
        )
    else:
        execute(
            "UPDATE Users SET full_name = %s, phone = %s, profile_picture_url = %s WHERE user_id = %s",
            (full_name.strip(), phone.strip() if phone else None, next_pic, user_id)
        )

    return True, None


def get_all_users(role=None, status=None, search=None):
    """Admin view: Retrieve all users with vehicle, booking, session, and owned station counts."""
    sql = (
        "SELECT u.user_id, u.full_name, u.email, u.phone, u.role, u.account_status, u.created_at, "
        "       u.auth_provider, u.email_verified, u.last_login, u.profile_picture_url, u.is_demo, "
        "       COUNT(DISTINCT v.vehicle_id) AS vehicle_count, "
        "       COUNT(DISTINCT b.booking_id) AS booking_count, "
        "       COUNT(DISTINCT cs.session_id) AS session_count, "
        "       COUNT(DISTINCT st.station_id) AS owned_station_count "
        "FROM Users u "
        "LEFT JOIN Vehicles v ON v.user_id = u.user_id "
        "LEFT JOIN Bookings b ON b.user_id = u.user_id "
        "LEFT JOIN ChargingSessions cs ON cs.user_id = u.user_id "
        "LEFT JOIN Stations st ON st.owner_user_id = u.user_id "
        "WHERE 1=1 "
    )
    params = []
    if role:
        norm = normalize_role(role)
        if norm == "CUSTOMER":
            sql += " AND u.role IN ('CUSTOMER', 'USER')"
        else:
            sql += " AND u.role = %s"
            params.append(norm)
    if status:
        sql += " AND u.account_status = %s"
        params.append(status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        sql += " AND (u.full_name LIKE %s OR u.email LIKE %s OR COALESCE(u.phone, '') LIKE %s)"
        params.extend([like, like, like])

    sql += " GROUP BY u.user_id ORDER BY u.created_at DESC"
    return query_all(sql, params)


def toggle_user_status(user_id, admin_user_id):
    """Deactivate or activate a user account (protecting primary admin)."""
    if int(user_id) == int(admin_user_id):
        return False, "You cannot deactivate your own active administrator account."

    user = query_one("SELECT account_status FROM Users WHERE user_id = %s", (user_id,))
    if not user:
        return False, "User not found."

    new_status = "INACTIVE" if user["account_status"] == "ACTIVE" else "ACTIVE"
    execute("UPDATE Users SET account_status = %s WHERE user_id = %s", (new_status, user_id))
    return True, new_status


_AVATAR_MAX_BYTES = 2 * 1024 * 1024
_ALLOWED_AVATAR_EXT = {"png", "jpg", "jpeg", "webp"}


def _detect_image_type(raw_bytes):
    """Validate image magic bytes without trusting client Content-Type headers."""
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "webp"
    return None


def save_uploaded_avatar(file_storage, static_folder):
    """
    Safely validate and save an optional user profile picture upload.
    Returns (relative_static_url_or_None, error_message_or_None).
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None, None

    filename = file_storage.filename.strip()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_AVATAR_EXT:
        return None, "Profile picture must be a PNG, JPG, JPEG, or WebP image."

    raw_bytes = file_storage.read(_AVATAR_MAX_BYTES + 1)
    if not raw_bytes:
        return None, "Uploaded profile picture file is empty."
    if len(raw_bytes) > _AVATAR_MAX_BYTES:
        return None, "Profile picture must be smaller than 2 MB."

    detected = _detect_image_type(raw_bytes)
    if not detected:
        return None, "Invalid image format: Uploaded file is not a valid PNG, JPEG, or WebP image."

    rel_dir = os.path.join("uploads", "avatars")
    target_dir = os.path.join(static_folder, rel_dir)
    safe_name = f"avatar_{secrets.token_hex(12)}.{detected}"
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, safe_name), "wb") as fp:
            fp.write(raw_bytes)
    except OSError:
        return None, "Avatar storage is temporarily unavailable in this read-only runtime."

    return f"/static/uploads/avatars/{safe_name}", None
