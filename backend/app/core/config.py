from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )
    app_name: str = "SIM Classroom Companion API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://classroom_app:classroom_local_dev@localhost:5432/classroom_companion"
    )
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    groq_api_key: str | None = None
    groq_model: str | None = None
    telegram_bot_token: str | None = None
    default_school_timezone: str = "Asia/Kolkata"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
