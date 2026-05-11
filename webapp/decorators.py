from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import abort, jsonify, request, session

from webapp.services import audit_log_service
from webapp.services.api_token_service import verify_token
from webapp.services.feature_flags import is_enabled
from webapp.services.market_hours_service import can_mutate


ROLE_ORDER = {"viewer": 0, "admin": 1, "super": 2, "superadmin": 3}


def current_user() -> dict[str, str]:
    return session.get("user") or {"username": "anonymous", "role": "viewer"}


def require_role(role: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if ROLE_ORDER.get(user.get("role", "viewer"), 0) < ROLE_ORDER[role]:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "forbidden"}), 403
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_feature(key: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_enabled(key, default=True):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "module disabled", "feature": key}), 503
                abort(503)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_module(key: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_enabled(key, default=False):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "module disabled", "module": key}), 503
                abort(404)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def market_hours_protected(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not can_mutate(user.get("role", "viewer")):
            audit_log_service.append("market_hours.blocked", user.get("username", "anonymous"), {"path": request.path})
            return jsonify({"error": "market hours protection active"}), 403
        return func(*args, **kwargs)

    return wrapper


def monitored_write_blocked(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if is_enabled("phase_readonly_mode", default=True):
            return jsonify({"error": "Phase parallel review: monitored-host writes are locked"}), 403
        return func(*args, **kwargs)

    return wrapper


def require_api_scope(scope: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            prefix = "Bearer "
            if not auth_header.startswith(prefix):
                return jsonify({"error": "missing bearer token"}), 401
            token = auth_header[len(prefix) :].strip()
            if not verify_token(token, scope):
                return jsonify({"error": "invalid token or scope"}), 403
            return func(*args, **kwargs)

        return wrapper

    return decorator
