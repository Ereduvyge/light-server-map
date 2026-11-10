"""Environment-based settings; an optional .env file is supported."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    DATABASE_URL: str | None = None
    MONITORING_ENABLED: bool = True
    SCHEDULE_SYNC_SECONDS: int = Field(default=10, ge=1)
    CHECK_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    CHECK_CONCURRENCY: int = Field(default=20, ge=1)
    LOG_LEVEL: str = "INFO"
    ADMIN_PASSWORD: SecretStr = Field(default=SecretStr("admin"), min_length=1)


config = Settings()
