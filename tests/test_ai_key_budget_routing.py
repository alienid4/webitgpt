from __future__ import annotations

from webapp.services import llm_provider


def test_choose_key_tier_falls_back_when_ai_disabled(monkeypatch):
    monkeypatch.setattr(
        llm_provider,
        "get_settings",
        lambda masked=True: {"enabled": False, "key_tiers": []},
    )

    decision = llm_provider.choose_key_tier(check_level="L3")

    assert decision["decision"] == "script_fallback"
    assert decision["selected_tier"] is None


def test_choose_key_tier_uses_l3_before_budget_limit(monkeypatch):
    monkeypatch.setattr(
        llm_provider,
        "get_settings",
        lambda masked=True: {
            "enabled": True,
            "monthly_budget_usd": 50,
            "fallback_strategy": "script_fallback",
            "key_tiers": [
                {"tier": "L1", "enabled": True, "monthly_limit_usd": 10, "max_check_level": "L1"},
                {"tier": "L2", "enabled": True, "monthly_limit_usd": 30, "max_check_level": "L2"},
                {"tier": "L3", "enabled": True, "monthly_limit_usd": 50, "max_check_level": "L3"},
            ],
        },
    )

    decision = llm_provider.choose_key_tier(check_level="L3", month_cost_usd=20, estimated_cost_usd=2)

    assert decision["decision"] == "use_tier"
    assert decision["selected_tier"]["tier"] == "L3"


def test_choose_key_tier_downgrades_when_global_budget_exceeded(monkeypatch):
    monkeypatch.setattr(
        llm_provider,
        "get_settings",
        lambda masked=True: {
            "enabled": True,
            "monthly_budget_usd": 25,
            "fallback_strategy": "script_fallback",
            "key_tiers": [
                {"tier": "L1", "enabled": True, "monthly_limit_usd": 100, "max_check_level": "L1"},
                {"tier": "L2", "enabled": True, "monthly_limit_usd": 100, "max_check_level": "L2"},
                {"tier": "L3", "enabled": True, "monthly_limit_usd": 100, "max_check_level": "L3"},
            ],
        },
    )

    decision = llm_provider.choose_key_tier(check_level="L3", month_cost_usd=24, estimated_cost_usd=3)

    assert decision["decision"] == "use_tier"
    assert decision["selected_tier"]["tier"] == "L1"
    assert decision["over_global_budget"] is True
