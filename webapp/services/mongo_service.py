from __future__ import annotations

from functools import lru_cache
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from webapp.config import MONGO_DB_NAME, MONGO_URI


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)


def get_db() -> Database:
    return get_client()[MONGO_DB_NAME]


def get_collection(name: str) -> Collection:
    return get_db()[name]


def ping() -> dict[str, Any]:
    get_client().admin.command("ping")
    return {"mongo": "ok", "db": MONGO_DB_NAME}

