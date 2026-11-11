"""Centralized settings via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    STORAGE_TYPE: str = "memory"
    CACHE_DIR: str = "/app/data/cache"
    IMAGES_DIR: str = "/app/data/images"
    CACHE_TTL_HOURS: int = 24

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
