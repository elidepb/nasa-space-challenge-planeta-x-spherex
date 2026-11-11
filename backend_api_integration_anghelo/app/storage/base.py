"""Abstract interface for session persistence (decouples storage backend)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID


class ISessionRepository(ABC):
    @abstractmethod
    async def save(self, session_data: dict) -> None:
        """Persist a session document."""

    @abstractmethod
    async def get_by_id(self, session_id: UUID) -> Optional[dict]:
        """Retrieve a session by its UUID."""

    @abstractmethod
    async def list_active(self) -> List[dict]:
        """List sessions still in processing state."""
