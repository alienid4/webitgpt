from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from webapp.services.mask_service import mask_dict, mask_text
from webapp.services.mongo_service import get_collection


CHANNELS = ["email", "slack", "teams", "jira", "webhook"]


def list_channels() -> list[dict[str, Any]]:
    configured = {doc["channel"]: doc for doc in get_collection("notification_channels").find({}, {"_id": 0})}
    return [
        {
            "channel": channel,
            "enabled": bool(configured.get(channel, {}).get("enabled", False)),
            "target": mask_text(str(configured.get(channel, {}).get("target", ""))),
            "updated_at": configured.get(channel, {}).get("updated_at"),
        }
        for channel in CHANNELS
    ]


def save_channel(channel: str, target: str, enabled: bool, user: str) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError("invalid channel")
    doc = {"channel": channel, "target": target, "enabled": bool(enabled), "updated_at": datetime.now(timezone.utc), "updated_by": user}
    get_collection("notification_channels").update_one({"channel": channel}, {"$set": doc}, upsert=True)
    return mask_dict(doc)


def send_test(channel: str, user: str) -> dict[str, Any]:
    doc = get_collection("notification_channels").find_one({"channel": channel}, {"_id": 0}) or {"enabled": False, "target": ""}
    result = {
        "channel": channel,
        "status": "queued" if doc.get("enabled") else "disabled",
        "target": mask_text(str(doc.get("target", ""))),
        "sent_at": datetime.now(timezone.utc),
        "user": user,
    }
    get_collection("notification_events").insert_one(result)
    result.pop("_id", None)
    return result
