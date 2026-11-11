"""MongoDB/Motor session repository (future storage backend).

Implemented behind ``ISessionRepository`` so the router and services never
change when ``STORAGE_TYPE=mongo``.  Motor connects lazily, so instantiating
this repository does not require a live MongoDB during the factory switch test.
"""

from __future__ import annotations

import os
from typing import List, Optional
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from app.storage.base import ISessionRepository


class MongoSessionRepository(ISessionRepository):
    def __init__(self):
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self._client = AsyncIOMotorClient(uri)
        self._collection = self._client["spherex"]["sessions"]

    async def save(self, session_data: dict) -> None:
        await self._collection.replace_one(
            {"_id": str(session_data["session_id"])},
            {**session_data, "_id": str(session_data["session_id"])},
            upsert=True,
        )

    async def get_by_id(self, session_id: UUID) -> Optional[dict]:
        doc = await self._collection.find_one({"_id": str(session_id)})
        if doc is None:
            return None
        doc["session_id"] = UUID(doc["_id"])
        return doc

    async def list_active(self) -> List[dict]:
        cursor = self._collection.find({"estado": "EN_PROCESO"})
        return [doc async for doc in cursor]
