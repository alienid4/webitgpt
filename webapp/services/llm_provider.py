from __future__ import annotations

from typing import Any, Optional

from webapp.services.mask_service import mask_dict
from webapp.services.mongo_service import get_collection


DEFAULT_SETTINGS = {
    "provider": "disabled",
    "base_url": "",
    "model": "",
    "api_key": "",
    "enabled": False,
}


def get_settings(masked: bool = True) -> dict[str, Any]:
    doc = get_collection("settings").find_one({"key": "ai_provider"}, {"_id": 0}) or {"value": DEFAULT_SETTINGS}
    value = {**DEFAULT_SETTINGS, **doc.get("value", {})}
    return mask_dict(value) if masked else value


def save_settings(settings: dict[str, Any], user: str = "system") -> dict[str, Any]:
    current = get_settings(masked=False)
    value = {
        "provider": settings.get("provider", current.get("provider", "disabled")),
        "base_url": settings.get("base_url", current.get("base_url", "")),
        "model": settings.get("model", current.get("model", "")),
        "api_key": settings.get("api_key") or current.get("api_key", ""),
        "enabled": bool(settings.get("enabled")),
        "updated_by": user,
    }
    get_collection("settings").update_one({"key": "ai_provider"}, {"$set": {"key": "ai_provider", "value": value}}, upsert=True)
    return mask_dict(value)


class LlmProvider:
    def chat(self, message: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        settings = get_settings(masked=True)
        if settings.get("enabled"):
            return {
                "provider": settings.get("provider"),
                "reply": f"AI provider settings are ready for {settings.get('provider')} / {settings.get('model')}. Phase 1 does not send prompts outside the review box.",
                "context_keys": sorted((context or {}).keys()),
                "echo": message,
            }
        return {
            "provider": settings.get("provider", "disabled"),
            "reply": "AI provider is not configured yet. Phase 1 chat panel is ready for provider settings.",
            "context_keys": sorted((context or {}).keys()),
            "echo": message,
        }


def get_provider() -> LlmProvider:
    return LlmProvider()
