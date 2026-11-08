"""In-memory session repository (default storage backend)."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.storage.base import ISessionRepository


class InMemorySessionRepository(ISessionRepository):
    def __init__(self):
        self._store: dict[UUID, dict] = {}

    async def save(self, session_data: dict) -> None:
        session_id = session_data["session_id"]
        self._store[session_id] = session_data

    async def get_by_id(self, session_id: UUID) -> Optional[dict]:
        return self._store.get(session_id)

    async def list_active(self) -> List[dict]:
        return [
            s for s in self._store.values() if s.get("estado") == "EN_PROCESO"
        ]
