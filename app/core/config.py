"""Application configuration.

Settings are loaded from environment variables and a local ``.env`` file via
``pydantic-settings``. Import the ``settings`` singleton rather than constructing
``Settings`` directly, so every module observes the same values.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: object) -> object:
    """Split a comma-separated environment string into a list of trimmed items."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], BeforeValidator(_split_csv)]


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
    CORS_ORIGINS: CsvList = ["http://localhost:5173"]

    # AI provider
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_DAILY_LIMIT: int = 20

    # Domain
    DEFAULT_CURRENCY: str = "BDT"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()


settings = get_settings()
