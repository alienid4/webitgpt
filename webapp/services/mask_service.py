from __future__ import annotations

import hashlib
import json
import re
from typing import Any


HOST_SENSITIVE_FIELDS = {"ssh_key", "password", "password_hash", "mfa_secret", "token", "api_key"}
PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key)\s*[:=]\s*\S+"), r"\1=***MASKED***"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "***IP_MASKED***"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.S), "***PRIVATE_KEY_MASKED***"),
]


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def mask_text(text: str) -> str:
    masked = text
    for pattern, repl in PATTERNS:
        masked = pattern.sub(repl, masked)
    return masked


def mask_dict(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key in HOST_SENSITIVE_FIELDS:
            result[key] = "***MASKED***"
        elif isinstance(value, dict):
            result[key] = mask_dict(value)
        elif isinstance(value, list):
            result[key] = [mask_dict(v) if isinstance(v, dict) else mask_text(str(v)) for v in value]
        elif isinstance(value, str):
            result[key] = mask_text(value)
        else:
            result[key] = value
    return result


def mask_json(data: Any) -> str:
    if isinstance(data, dict):
        data = mask_dict(data)
    return mask_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))

