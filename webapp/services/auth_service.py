from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pyotp
import secrets
from werkzeug.security import check_password_hash, generate_password_hash

from webapp.services.mongo_service import get_collection


ROLES = {"viewer", "admin", "super", "superadmin"}


def create_user(username: str, password: str, role: str = "viewer", **extra: Any) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError("invalid role")
    now = datetime.now(timezone.utc)
    doc = {
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "display_name": extra.get("display_name", username),
        "email": extra.get("email", ""),
        "must_change": extra.get("must_change", False),
        "mfa_enabled": extra.get("mfa_enabled", False),
        "mfa_secret": extra.get("mfa_secret"),
        "locked": False,
        "failed_login_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    get_collection("users").insert_one(doc)
    doc["_id"] = str(doc["_id"])
    doc.pop("password_hash", None)
    doc.pop("mfa_secret", None)
    return doc


def verify_login(username: str, password: str, otp: Optional[str] = None) -> Optional[dict[str, Any]]:
    user = get_collection("users").find_one({"username": username})
    if not user or user.get("locked"):
        return None
    if not check_password_hash(user.get("password_hash", ""), password):
        get_collection("users").update_one({"username": username}, {"$inc": {"failed_login_count": 1}})
        return None
    # OTP/MFA login verification is disabled for the current development phase.
    get_collection("users").update_one(
        {"username": username},
        {"$set": {"last_login_at": datetime.now(timezone.utc), "failed_login_count": 0}},
    )
    return public_user(user)


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "role": user.get("role", "viewer"),
        "must_change": bool(user.get("must_change")),
        "mfa_enabled": bool(user.get("mfa_enabled")),
        "email": user.get("email", ""),
        "locked": bool(user.get("locked")),
        "failed_login_count": int(user.get("failed_login_count", 0)),
    }


def get_user(username: str) -> Optional[dict[str, Any]]:
    user = get_collection("users").find_one({"username": username})
    return public_user(user) if user else None


def begin_mfa_setup(username: str) -> dict[str, str]:
    user = get_collection("users").find_one({"username": username})
    if not user:
        raise KeyError("user not found")
    secret = user.get("mfa_pending_secret") or pyotp.random_base32()
    get_collection("users").update_one(
        {"username": username},
        {"$set": {"mfa_pending_secret": secret, "updated_at": datetime.now(timezone.utc)}},
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="webitgpt")
    return {"secret": secret, "uri": uri}


def confirm_mfa_setup(username: str, otp: str) -> bool:
    user = get_collection("users").find_one({"username": username})
    secret = (user or {}).get("mfa_pending_secret")
    if not secret or not pyotp.TOTP(secret).verify(otp):
        return False
    get_collection("users").update_one(
        {"username": username},
        {
            "$set": {"mfa_enabled": True, "mfa_secret": secret, "updated_at": datetime.now(timezone.utc)},
            "$unset": {"mfa_pending_secret": ""},
        },
    )
    return True


def disable_mfa(username: str) -> None:
    get_collection("users").update_one(
        {"username": username},
        {
            "$set": {"mfa_enabled": False, "updated_at": datetime.now(timezone.utc)},
            "$unset": {"mfa_secret": "", "mfa_pending_secret": ""},
        },
    )


def list_users() -> list[dict[str, Any]]:
    return [public_user(user) for user in get_collection("users").find({}).sort("username", 1)]


def upsert_user(username: str, role: str, email: str = "", display_name: str = "", password: str = "", user: str = "system") -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError("invalid role")
    now = datetime.now(timezone.utc)
    update = {
        "username": username,
        "role": role,
        "email": email,
        "display_name": display_name or username,
        "updated_at": now,
        "updated_by": user,
        "locked": False,
    }
    if password:
        update["password_hash"] = generate_password_hash(password)
        update["must_change"] = True
    get_collection("users").update_one(
        {"username": username},
        {"$set": update, "$setOnInsert": {"created_at": now, "failed_login_count": 0, "mfa_enabled": False}},
        upsert=True,
    )
    return get_user(username) or {}


def set_user_locked(username: str, locked: bool, user: str = "system") -> bool:
    result = get_collection("users").update_one(
        {"username": username},
        {"$set": {"locked": bool(locked), "updated_at": datetime.now(timezone.utc), "updated_by": user}},
    )
    return result.matched_count == 1


def reset_password(username: str, user: str = "system") -> dict[str, str]:
    password = f"Reset-{secrets.token_urlsafe(8)}"
    result = get_collection("users").update_one(
        {"username": username},
        {
            "$set": {
                "password_hash": generate_password_hash(password),
                "must_change": True,
                "failed_login_count": 0,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": user,
            }
        },
    )
    if result.matched_count != 1:
        raise KeyError("user not found")
    return {"username": username, "temporary_password": password}


def generate_backup_codes(username: str, count: int = 8) -> dict[str, object]:
    codes = [secrets.token_hex(4).upper() for _ in range(count)]
    get_collection("users").update_one(
        {"username": username},
        {"$set": {"backup_codes": [generate_password_hash(code) for code in codes], "updated_at": datetime.now(timezone.utc)}},
    )
    return {"username": username, "backup_codes": codes}
