from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Bulk Certificate Generator API"
    ENV: str = "development"
    DEBUG: bool = True

    # Database configuration (SQLite by default, PostgreSQL supported)
    DATABASE_URL: str = "sqlite:///./certificates.db"

    # Storage configuration for generated PDF certificates
    STORAGE_DIR: str = "./storage"

    # Worker and limits configuration
    MAX_RECIPIENTS_PER_REQUEST: int = 5000
    WORKER_THREADS: int = 4
    SYNC_WORKER: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
