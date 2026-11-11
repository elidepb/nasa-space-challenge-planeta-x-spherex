"""Session repository factory switched by the STORAGE_TYPE env var."""

from __future__ import annotations

import os
from typing import Optional

from app.storage.base import ISessionRepository
from app.storage.memory_repository import InMemorySessionRepository


class SessionRepositoryFactory:
    _instance: Optional[ISessionRepository] = None

    @classmethod
    def get_repository(cls) -> ISessionRepository:
        if cls._instance is None:
            storage_type = os.getenv("STORAGE_TYPE", "memory").lower()
            if storage_type == "mongo":
                from app.storage.mongo_repository import MongoSessionRepository  # noqa: F401

                cls._instance = MongoSessionRepository()
            else:
                cls._instance = InMemorySessionRepository()
        return cls._instance
