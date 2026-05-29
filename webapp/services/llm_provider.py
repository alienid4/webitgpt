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
    "budget_policy_enabled": False,
    "monthly_budget_usd": 0.0,
    "fallback_strategy": "script_fallback",
    "key_tiers": [
        {
            "tier": "L1",
            "label": "L1 低成本",
            "model": "",
            "api_key": "",
            "monthly_limit_usd": 0.0,
            "max_check_level": "L1",
            "enabled": False,
        },
        {
            "tier": "L2",
            "label": "L2 一般分析",
            "model": "",
            "api_key": "",
            "monthly_limit_usd": 0.0,
            "max_check_level": "L2",
            "enabled": False,
        },
        {
            "tier": "L3",
            "label": "L3 深度判讀",
            "model": "",
            "api_key": "",
            "monthly_limit_usd": 0.0,
            "max_check_level": "L3",
            "enabled": False,
        },
    ],
}

CHECK_LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3}


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return default


def _normalize_tiers(settings: dict[str, Any], current: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current_by_tier = {item.get("tier"): item for item in (current or {}).get("key_tiers", []) if isinstance(item, dict)}
    incoming = settings.get("key_tiers")
    if not isinstance(incoming, list):
        incoming = DEFAULT_SETTINGS["key_tiers"]
    tiers: list[dict[str, Any]] = []
    for index, default in enumerate(DEFAULT_SETTINGS["key_tiers"]):
        raw = incoming[index] if index < len(incoming) and isinstance(incoming[index], dict) else {}
        existing = current_by_tier.get(default["tier"], {})
        tiers.append(
            {
                "tier": default["tier"],
                "label": raw.get("label") or existing.get("label") or default["label"],
                "model": raw.get("model") or existing.get("model") or default["model"],
                "api_key": raw.get("api_key") or existing.get("api_key") or default["api_key"],
                "monthly_limit_usd": _float_value(raw.get("monthly_limit_usd", existing.get("monthly_limit_usd", 0))),
                "max_check_level": raw.get("max_check_level") or existing.get("max_check_level") or default["max_check_level"],
                "enabled": bool(raw.get("enabled")),
            }
        )
    return tiers


def get_settings(masked: bool = True) -> dict[str, Any]:
    doc = get_collection("settings").find_one({"key": "ai_provider"}, {"_id": 0}) or {"value": DEFAULT_SETTINGS}
    value = {**DEFAULT_SETTINGS, **doc.get("value", {})}
    value["key_tiers"] = _normalize_tiers(value, value)
    return mask_dict(value) if masked else value


def save_settings(settings: dict[str, Any], user: str = "system") -> dict[str, Any]:
    current = get_settings(masked=False)
    value = {
        "provider": settings.get("provider", current.get("provider", "disabled")),
        "base_url": settings.get("base_url", current.get("base_url", "")),
        "model": settings.get("model", current.get("model", "")),
        "api_key": settings.get("api_key") or current.get("api_key", ""),
        "enabled": bool(settings.get("enabled")),
        "budget_policy_enabled": bool(settings.get("budget_policy_enabled")),
        "monthly_budget_usd": _float_value(settings.get("monthly_budget_usd", current.get("monthly_budget_usd", 0))),
        "fallback_strategy": settings.get("fallback_strategy", current.get("fallback_strategy", "script_fallback")),
        "key_tiers": _normalize_tiers(settings, current),
        "updated_by": user,
    }
    get_collection("settings").update_one({"key": "ai_provider"}, {"$set": {"key": "ai_provider", "value": value}}, upsert=True)
    return mask_dict(value)


def choose_key_tier(check_level: str = "L1", month_cost_usd: float = 0.0, estimated_cost_usd: float = 0.0) -> dict[str, Any]:
    settings = get_settings(masked=True)
    level = str(check_level or "L1").upper()
    requested_rank = CHECK_LEVEL_ORDER.get(level, 1)
    projected_cost = _float_value(month_cost_usd) + _float_value(estimated_cost_usd)
    monthly_budget = _float_value(settings.get("monthly_budget_usd"))
    enabled_tiers = [tier for tier in settings.get("key_tiers", []) if tier.get("enabled")]
    if not settings.get("enabled") or not enabled_tiers:
        return {
            "decision": "script_fallback",
            "reason": "AI provider or key tier is not enabled.",
            "check_level": level,
            "selected_tier": None,
            "projected_cost_usd": projected_cost,
        }
    candidates = [
        tier
        for tier in enabled_tiers
        if CHECK_LEVEL_ORDER.get(str(tier.get("max_check_level", "L1")).upper(), 1) >= requested_rank
    ]
    if not candidates:
        candidates = enabled_tiers
    over_global_budget = monthly_budget > 0 and projected_cost > monthly_budget
    if over_global_budget:
        candidates = [tier for tier in enabled_tiers if str(tier.get("tier")).upper() in {"L1", "L2"}] or enabled_tiers
    for tier in candidates:
        tier_limit = _float_value(tier.get("monthly_limit_usd"))
        if tier_limit <= 0 or projected_cost <= tier_limit:
            return {
                "decision": "use_tier",
                "reason": "Selected by check level and budget policy.",
                "check_level": level,
                "selected_tier": tier,
                "projected_cost_usd": projected_cost,
                "over_global_budget": over_global_budget,
            }
    return {
        "decision": settings.get("fallback_strategy") or "script_fallback",
        "reason": "All enabled key tiers exceed configured budget.",
        "check_level": level,
        "selected_tier": None,
        "projected_cost_usd": projected_cost,
        "over_global_budget": over_global_budget,
    }


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
