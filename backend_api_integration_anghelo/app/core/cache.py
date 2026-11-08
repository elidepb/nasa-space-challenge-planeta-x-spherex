"""Startup check that data volumes exist."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


def ensure_data_volumes() -> None:
    """Create /app/data/cache and /app/data/images if missing."""
    for path in (settings.CACHE_DIR, settings.IMAGES_DIR):
        Path(path).mkdir(parents=True, exist_ok=True)
