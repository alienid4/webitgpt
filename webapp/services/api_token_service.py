from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from webapp.services.mongo_service import get_collection


def issue_token(name: str, scopes: list[str], created_by: str) -> dict[str, str]:
    raw = f"wgpt_{secrets.token_urlsafe(32)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    get_collection("api_tokens").insert_one(
        {
            "name": name,
            "token_hash": digest,
            "scopes": scopes,
            "active": True,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return {"token": raw}


def verify_token(raw: str, scope: str) -> bool:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    doc = get_collection("api_tokens").find_one({"token_hash": digest, "active": True})
    return bool(doc and scope in doc.get("scopes", []))

