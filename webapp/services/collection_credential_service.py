from __future__ import annotations

from typing import Any

from webapp.services.mongo_service import get_collection


DEFAULT_TIERS = [
    {
        "tier": "L1",
        "name": "探測帳號",
        "account": "itwebL1",
        "auth_method": "ssh_key_or_pam",
        "scope": "全域",
        "enabled": True,
        "sudo_policy": "none",
        "purpose": "確認連通、主機名稱、OS 線索與常見服務，不讀敏感資料。",
        "permission": "低權限，不允許 sudo 或寫入。",
        "examples": "ping、port、hostname、banner、基本 health check",
    },
    {
        "tier": "L2",
        "name": "盤點帳號",
        "account": "itwebL2",
        "auth_method": "pam",
        "scope": "全域",
        "enabled": True,
        "sudo_policy": "full",
        "purpose": "讀取資產盤點需要的 OS、套件、服務、帳號與效能資訊。",
        "permission": "sudo 權限；日後交由 PAM 納管與稽核。",
        "examples": "os-release、systemctl、套件清單、帳號清單、NMON/效能資料",
    },
    {
        "tier": "L3",
        "name": "深度檢查帳號",
        "account": "itwebL3",
        "auth_method": "pam_approval",
        "scope": "需審核",
        "enabled": False,
        "sudo_policy": "full",
        "purpose": "事件排查時讀取 log、程序、網路與核心狀態，用於深度診斷。",
        "permission": "高權限，需 PAM、審核、時間限制與稽核紀錄。",
        "examples": "journal、kernel、process、socket、AP 服務狀態",
    },
]


def _settings_collection():
    return get_collection("settings")


def _normalize_tier(raw: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    account = str(raw.get("account") or default["account"]).strip() or default["account"]
    auth_method = str(raw.get("auth_method") or default["auth_method"]).strip() or default["auth_method"]
    scope = str(raw.get("scope") or default["scope"]).strip() or default["scope"]
    return {
        **default,
        "account": account,
        "auth_method": auth_method,
        "scope": scope,
        "enabled": bool(raw.get("enabled")),
    }


def get_collection_credentials() -> dict[str, Any]:
    doc = _settings_collection().find_one({"key": "collection_credentials"}, {"_id": 0}) or {}
    value = doc.get("value") or {}
    current = {item.get("tier"): item for item in value.get("tiers", []) if isinstance(item, dict)}
    tiers = [_normalize_tier(current.get(default["tier"], {}), default) for default in DEFAULT_TIERS]
    return {
        "tiers": tiers,
        "updated_by": value.get("updated_by", ""),
        "updated_at": value.get("updated_at", ""),
    }


def save_collection_credentials(payload: dict[str, Any], user: str) -> dict[str, Any]:
    tiers = []
    for default in DEFAULT_TIERS:
        tier = default["tier"]
        tiers.append(
            _normalize_tier(
                {
                    "account": payload.get(f"{tier}_account"),
                    "auth_method": payload.get(f"{tier}_auth_method"),
                    "scope": payload.get(f"{tier}_scope"),
                    "enabled": payload.get(f"{tier}_enabled") == "on",
                },
                default,
            )
        )
    value = {
        "tiers": tiers,
        "updated_by": user,
    }
    _settings_collection().update_one(
        {"key": "collection_credentials"},
        {"$set": {"key": "collection_credentials", "value": value}},
        upsert=True,
    )
    return get_collection_credentials()


def linux_bootstrap_script(settings: dict[str, Any] | None = None) -> str:
    settings = settings or get_collection_credentials()
    tiers = settings.get("tiers", DEFAULT_TIERS)
    account_by_tier = {item["tier"]: item.get("account") or f"itweb{item['tier']}" for item in tiers}
    l1 = account_by_tier.get("L1", "itwebL1")
    l2 = account_by_tier.get("L2", "itwebL2")
    l3 = account_by_tier.get("L3", "itwebL3")
    password = "1qaz@WSX"
    sudoers_path = "/etc/sudoers.d/webitgpt-collection"
    return f"""#!/usr/bin/env bash
set -euo pipefail

# webitgpt collection account bootstrap
# Run as root on each Linux client. Existing accounts are detected and skipped.
DEFAULT_PASSWORD='{password}'
SUDOERS_FILE='{sudoers_path}'

ensure_account() {{
  local user=\"$1\"
  if id \"$user\" >/dev/null 2>&1; then
    echo \"SKIP existing account: $user\"
  else
    useradd -m -s /bin/bash \"$user\"
    echo \"$user:$DEFAULT_PASSWORD\" | chpasswd
    echo \"CREATED account: $user\"
  fi
}}

ensure_account '{l1}'
ensure_account '{l2}'
ensure_account '{l3}'

cat > \"$SUDOERS_FILE\" <<'SUDOERS'
# Managed by webitgpt. L1 has no sudo. L2/L3 are temporary sudo accounts until PAM takeover.
{l2} ALL=(ALL) ALL
{l3} ALL=(ALL) ALL
SUDOERS
chmod 0440 \"$SUDOERS_FILE\"
visudo -cf \"$SUDOERS_FILE\"

echo \"DONE webitgpt collection accounts checked/created.\"
echo \"Temporary password: {password}\"
echo \"Next: hand over L2/L3 to PAM and rotate the password.\"
"""
