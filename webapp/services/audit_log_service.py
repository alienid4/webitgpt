from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from webapp.services.mongo_service import get_collection


def append(action: str, user: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    col = get_collection("audit_logs")
    last = col.find_one({}, sort=[("seq", -1)])
    seq = (last["seq"] if last else 0) + 1
    prev_hash = last["hash"] if last else "GENESIS"
    payload = json.dumps(
        {
            "seq": seq,
            "user": user,
            "action": action,
            "details": details or {},
            "prev_hash": prev_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    doc = {
        "seq": seq,
        "user": user,
        "action": action,
        "details": details or {},
        "prev_hash": prev_hash,
        "hash": digest,
        "ts": datetime.now(timezone.utc),
    }
    col.insert_one(doc)
    return {**doc, "_id": str(doc["_id"])}


def verify_chain() -> dict[str, Any]:
    expected_prev = "GENESIS"
    count = 0
    for doc in get_collection("audit_logs").find({}).sort("seq", 1):
        payload = json.dumps(
            {
                "seq": doc["seq"],
                "user": doc["user"],
                "action": doc["action"],
                "details": doc.get("details", {}),
                "prev_hash": doc["prev_hash"],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if doc["prev_hash"] != expected_prev:
            return {"ok": False, "count": count, "error": f"prev_hash mismatch at seq {doc['seq']}"}
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if digest != doc["hash"]:
            return {"ok": False, "count": count, "error": f"hash mismatch at seq {doc['seq']}"}
        expected_prev = doc["hash"]
        count += 1
    return {"ok": True, "count": count}
