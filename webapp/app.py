from __future__ import annotations

import uuid

from flask import Flask, g, request, session

from webapp import config
from webapp.decorators import current_user
from webapp.services.auth_service import get_user
from webapp.services.feature_flags import is_enabled
from webapp.routes import (
    api_admin,
    api_ai,
    api_compliance,
    api_debug,
    api_deep_check,
    api_dependencies,
    api_edge,
    api_housekeeping,
    api_inventory,
    api_hosts,
    api_mcp,
    api_notifications,
    api_operations,
    api_platforms,
    api_reports,
    api_self_check,
    api_superadmin,
    api_v1,
    auth,
    system,
)


def create_app() -> Flask:
    config.ensure_runtime_dirs()
    app = Flask(__name__)
    app.config.from_mapping(SECRET_KEY=config.SECRET_KEY)

    @app.before_request
    def attach_trace_id() -> None:
        g.trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        if (
            request.endpoint != "auth.logout"
            and request.endpoint not in {"auth.login_page", "auth.login"}
            and not request.endpoint == "static"
            and not (request.endpoint or "").startswith("system.")
            and "user" not in session
            and not session.get("dev_auto_login_suspended")
            and is_enabled("dev_auto_login_superadmin", default=True)
        ):
            try:
                user = get_user("superadmin")
            except Exception:
                user = None
            if user:
                session["user"] = user

    @app.after_request
    def add_trace_id(response):
        response.headers["X-Trace-Id"] = g.get("trace_id", "")
        if response.content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.context_processor
    def inject_globals():
        return {
            "current_user": current_user(),
            "app_name": config.APP_NAME,
            "app_version": config.VERSION,
            "patch_id": config.PATCH_ID,
            "release_note": config.RELEASE_NOTE,
            "build_time": config.BUILD_TIME,
            "feature_enabled": is_enabled,
        }

    app.register_blueprint(system.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api_hosts.bp)
    app.register_blueprint(api_self_check.bp)
    app.register_blueprint(api_debug.bp)
    app.register_blueprint(api_deep_check.bp)
    app.register_blueprint(api_dependencies.bp)
    app.register_blueprint(api_v1.bp)
    app.register_blueprint(api_ai.bp)
    app.register_blueprint(api_edge.bp)
    app.register_blueprint(api_admin.bp)
    app.register_blueprint(api_superadmin.bp)
    app.register_blueprint(api_compliance.bp)
    app.register_blueprint(api_housekeeping.bp)
    app.register_blueprint(api_inventory.bp)
    app.register_blueprint(api_notifications.bp)
    app.register_blueprint(api_reports.bp)
    app.register_blueprint(api_platforms.bp)
    app.register_blueprint(api_operations.bp)
    app.register_blueprint(api_mcp.bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.WEB_PORT, debug=True)
