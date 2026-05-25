from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from webapp.services.mongo_service import get_collection


DEFAULT_PRICE_TABLE = [
    {
        "provider": "OpenAI",
        "model": "default",
        "input_per_1m_usd": 1.00,
        "output_per_1m_usd": 4.00,
        "note": "預設估算價，正式接 API 後請依實際模型價格調整。",
    },
    {
        "provider": "Internal",
        "model": "company-gpt",
        "input_per_1m_usd": 0.00,
        "output_per_1m_usd": 0.00,
        "note": "公司內部 GPT 若無直接計費，可先以 0 元列管用量。",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_key(value: Optional[datetime] = None) -> str:
    target = value or _now()
    return target.strftime("%Y-%m")


def _day_key(value: Optional[datetime] = None) -> str:
    target = value or _now()
    return target.strftime("%m/%d")


def _price_for(model: str = "", provider: str = "") -> dict[str, Any]:
    model_text = (model or "").lower()
    provider_text = (provider or "").lower()
    for row in DEFAULT_PRICE_TABLE:
        if row["model"].lower() == model_text or row["provider"].lower() == provider_text:
            return row
    return DEFAULT_PRICE_TABLE[0]


def estimate_cost_usd(input_tokens: int = 0, output_tokens: int = 0, model: str = "", provider: str = "") -> float:
    price = _price_for(model=model, provider=provider)
    input_cost = max(int(input_tokens or 0), 0) * float(price["input_per_1m_usd"]) / 1_000_000
    output_cost = max(int(output_tokens or 0), 0) * float(price["output_per_1m_usd"]) / 1_000_000
    return round(input_cost + output_cost, 6)


def record_usage(
    action: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    actor: str = "system",
    provider: str = "OpenAI",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    occurred_at = _now()
    total_tokens = max(int(input_tokens or 0), 0) + max(int(output_tokens or 0), 0)
    doc = {
        "occurred_at": occurred_at,
        "month": _month_key(occurred_at),
        "day": _day_key(occurred_at),
        "provider": provider or "OpenAI",
        "model": model or "default",
        "action": action or "unknown",
        "actor": actor or "system",
        "input_tokens": max(int(input_tokens or 0), 0),
        "output_tokens": max(int(output_tokens or 0), 0),
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimate_cost_usd(input_tokens, output_tokens, model=model, provider=provider),
        "metadata": metadata or {},
    }
    result = get_collection("ai_token_usage").insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def _aggregate_sum(match: dict[str, Any]) -> dict[str, Any]:
    result = list(
        get_collection("ai_token_usage").aggregate(
            [
                {"$match": match},
                {
                    "$group": {
                        "_id": None,
                        "input_tokens": {"$sum": "$input_tokens"},
                        "output_tokens": {"$sum": "$output_tokens"},
                        "total_tokens": {"$sum": "$total_tokens"},
                        "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                        "calls": {"$sum": 1},
                    }
                },
            ]
        )
    )
    if not result:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, "calls": 0}
    row = result[0]
    return {
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "total_tokens": int(row.get("total_tokens") or 0),
        "estimated_cost_usd": round(float(row.get("estimated_cost_usd") or 0), 4),
        "calls": int(row.get("calls") or 0),
    }


def _group_by(month: str, field: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = list(
        get_collection("ai_token_usage").aggregate(
            [
                {"$match": {"month": month}},
                {
                    "$group": {
                        "_id": f"${field}",
                        "input_tokens": {"$sum": "$input_tokens"},
                        "output_tokens": {"$sum": "$output_tokens"},
                        "total_tokens": {"$sum": "$total_tokens"},
                        "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                        "calls": {"$sum": 1},
                    }
                },
                {"$sort": {"total_tokens": -1, "estimated_cost_usd": -1}},
                {"$limit": limit},
            ]
        )
    )
    return [
        {
            "name": row.get("_id") or "-",
            "input_tokens": int(row.get("input_tokens") or 0),
            "output_tokens": int(row.get("output_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
            "estimated_cost_usd": round(float(row.get("estimated_cost_usd") or 0), 4),
            "calls": int(row.get("calls") or 0),
        }
        for row in rows
    ]


def token_cost_report(month: Optional[str] = None) -> dict[str, Any]:
    month = month or _month_key()
    summary = _aggregate_sum({"month": month})
    by_day = _group_by(month, "day", limit=31)
    by_action = _group_by(month, "action", limit=20)
    by_model = _group_by(month, "model", limit=20)
    recent = list(
        get_collection("ai_token_usage")
        .find({"month": month}, {"_id": 0})
        .sort("occurred_at", -1)
        .limit(50)
    )
    for item in recent:
        if hasattr(item.get("occurred_at"), "isoformat"):
            item["occurred_at"] = item["occurred_at"].isoformat()
    top_action = by_action[0] if by_action else {"name": "-", "total_tokens": 0, "estimated_cost_usd": 0, "calls": 0}
    return {
        "month": month,
        "summary": summary,
        "top_action": top_action,
        "by_day": sorted(by_day, key=lambda row: row["name"]),
        "by_action": by_action,
        "by_model": by_model,
        "recent": recent,
        "price_table": DEFAULT_PRICE_TABLE,
        "note": "費用為預估值；正式接上 API 後，請依模型供應商實際價格更新。",
    }
