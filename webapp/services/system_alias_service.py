from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any


SYSTEM_NAME_FIELDS = ("system_name", "asset_name", "device_type", "group_name", "apid")

CONFUSABLE_REPLACEMENTS = (
    ("證卷", "證券"),
    ("証券", "證券"),
    ("証卷", "證券"),
)

OPENING_CHECK_PLATFORMS = {"linux", "windows", "aix", "as400"}


def normalize_system_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    for source, target in CONFUSABLE_REPLACEMENTS:
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text).strip()


def system_match_key(value: Any) -> str:
    text = normalize_system_text(value).casefold()
    return re.sub(r"[\s\-_()\[\]{}.,;:|/\\]+", "", text)


def system_name_candidates(host: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for field in SYSTEM_NAME_FIELDS:
        value = normalize_system_text(host.get(field))
        if value and value not in {"-", "N/A"} and value not in seen:
            candidates.append(value)
            seen.add(value)
    return candidates


def canonical_host_system_name(host: dict[str, Any], default: str = "未分類系統") -> str:
    candidates = system_name_candidates(host)
    return candidates[0] if candidates else default


def host_matches_system(host: dict[str, Any], requested_system: str) -> bool:
    requested_key = system_match_key(requested_system)
    if not requested_key:
        return True
    return any(system_match_key(candidate) == requested_key for candidate in system_name_candidates(host))


def grouped_system_options(hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for host in hosts:
        candidates = system_name_candidates(host)
        display_name = candidates[0] if candidates else "未分類系統"
        key = system_match_key(display_name)
        if not key:
            continue
        item = grouped.setdefault(
            key,
            {
                "key": key,
                "name": display_name,
                "count": 0,
                "aliases": Counter(),
                "platforms": Counter(),
            },
        )
        item["count"] += 1
        item["platforms"][str(host.get("host_type") or "unknown")] += 1
        for candidate in candidates:
            item["aliases"][candidate] += 1

    rows: list[dict[str, Any]] = []
    for item in grouped.values():
        aliases: Counter = item["aliases"]
        canonical_name = sorted(aliases.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]
        rows.append(
            {
                "key": item["key"],
                "name": canonical_name,
                "count": item["count"],
                "alias_count": len(aliases),
                "aliases": [name for name, _count in aliases.most_common(6) if name != canonical_name],
                "platforms": dict(item["platforms"]),
            }
        )
    return sorted(rows, key=lambda item: (-item["count"], item["name"]))


def resolve_selected_system(system_name: str, options: list[dict[str, Any]], all_value: str = "__all__") -> str:
    requested = normalize_system_text(system_name)
    if not requested or requested == all_value:
        return ""
    requested_key = system_match_key(requested)
    for option in options:
        if requested_key in {str(option.get("key") or ""), system_match_key(option.get("name"))}:
            return str(option.get("key") or "")
        for alias in option.get("aliases") or []:
            if system_match_key(alias) == requested_key:
                return str(option.get("key") or "")
    return ""


def selected_system_label(selected_key: str, options: list[dict[str, Any]]) -> str:
    for option in options:
        if str(option.get("key") or "") == selected_key:
            return str(option.get("name") or selected_key)
    return "全部系統"


def opening_scope_summary(hosts: list[dict[str, Any]]) -> dict[str, Any]:
    active_hosts = [host for host in hosts if str(host.get("status") or "").lower() == "active"]
    opening_hosts: list[dict[str, Any]] = []
    excluded_hosts: list[dict[str, Any]] = []
    for host in active_hosts:
        host_type = str(host.get("host_type") or "").lower()
        if host_type in OPENING_CHECK_PLATFORMS:
            opening_hosts.append(host)
        else:
            excluded_hosts.append(host)
    opening_counter = Counter(str(host.get("host_type") or "unknown").lower() for host in opening_hosts)
    excluded_counter = Counter(str(host.get("host_type") or "unknown").lower() for host in excluded_hosts)
    return {
        "active_total": len(active_hosts),
        "opening_candidate_total": len(opening_hosts),
        "excluded_total": len(excluded_hosts),
        "opening_by_platform": dict(sorted(opening_counter.items())),
        "excluded_by_platform": dict(sorted(excluded_counter.items())),
        "note": "開門檢查只納入 Linux、Windows、AIX、AS400 主機；端點、網路設備與 VMware host 仍在 CMDB，但不跑 L1 主機巡檢。",
    }
