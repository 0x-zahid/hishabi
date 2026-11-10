"""Application configuration.

Settings are loaded from environment variables and a local ``.env`` file via
``pydantic-settings``. Import the ``settings`` singleton rather than constructing
``Settings`` directly, so every module observes the same values.
"""

import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Hishabi backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg://hishabi:password@localhost:5432/hishabi"
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://hishabi:password@localhost:5432/hishabi_test"
    )

    # Authentication
    JWT_SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # HTTP
    # NoDecode stops pydantic-settings from JSON-decoding the raw env value,
    # so the validator below sees the string exactly as it was written.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # AI provider
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_DAILY_LIMIT: int = 20

    # Domain
    DEFAULT_CURRENCY: str = "BDT"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept CORS_ORIGINS as a JSON list or a plain comma-separated string.

        ``NoDecode`` hands this validator the raw environment value, so both
        supported spellings arrive here as text:

        - a JSON list, e.g. ``["http://localhost:5173"]``
        - a plain comma-separated string, e.g. ``http://localhost:5173``

        A JSON list is decoded and its entries are trimmed. A plain string is
        split on commas. Empty and whitespace-only segments are dropped, and an
        entirely empty value yields an empty list.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    decoded = json.loads(stripped)
                except json.JSONDecodeError:
                    decoded = None
                if isinstance(decoded, list):
                    return [str(item).strip() for item in decoded if str(item).strip()]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()


settings = get_settings()
