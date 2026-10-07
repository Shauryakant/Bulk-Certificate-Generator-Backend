from functools import lru_cache

from pydantic import field_validator
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

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+psycopg2://", 1)
            if v.startswith("postgresql://") and "+psycopg2" not in v and "+psycopg" not in v:
                return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
