from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from webapp.decorators import current_user, require_feature, require_role
from webapp.services import audit_log_service
from webapp.services.notification_service import list_channels, save_channel, send_test

bp = Blueprint("api_notifications", __name__)


@bp.get("/notifications")
@require_feature("notify_email")
@require_role("superadmin")
def notifications_page():
    return render_template("notifications.html", channels=list_channels())


@bp.post("/notifications")
@require_feature("notify_email")
@require_role("superadmin")
def save_channel_page():
    doc = save_channel(request.form.get("channel", "email"), request.form.get("target", ""), request.form.get("enabled") == "on", current_user()["username"])
    audit_log_service.append("notification.channel.save", current_user()["username"], {"channel": doc["channel"], "enabled": doc["enabled"]})
    return redirect(url_for("api_notifications.notifications_page"))


@bp.post("/notifications/test/<channel>")
@require_feature("notify_email")
@require_role("superadmin")
def send_test_page(channel: str):
    result = send_test(channel, current_user()["username"])
    audit_log_service.append("notification.test", current_user()["username"], {"channel": channel, "status": result["status"]})
    return redirect(url_for("api_notifications.notifications_page"))


@bp.get("/api/notifications/channels")
@require_feature("notify_email")
@require_role("superadmin")
def channels_api():
    return jsonify({"items": list_channels()})


@bp.post("/api/notifications/test/<channel>")
@require_feature("notify_email")
@require_role("superadmin")
def send_test_api(channel: str):
    result = send_test(channel, current_user()["username"])
    audit_log_service.append("notification.test", current_user()["username"], {"channel": channel, "status": result["status"]})
    return jsonify(result)
