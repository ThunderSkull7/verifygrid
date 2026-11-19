from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_INSECURE_SECRET_KEY = "verifygrid-default-insecure-secret-key-change-in-production-12345"


class Settings(BaseSettings):
    verifygrid_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "VerifyGrid"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database configuration
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/verifygrid"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_connect_timeout: int = 5

    # Uploads remain local for the MVP. Production storage will be object storage.
    storage_root: Path = Path("storage/uploads")
    max_upload_bytes: int = 25 * 1024 * 1024

    # Authentication & Security
    secret_key: str = DEFAULT_INSECURE_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # CORS configuration (comma-separated or list of allowed origins)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if (
            self.verifygrid_env == "production"
            and self.secret_key == DEFAULT_INSECURE_SECRET_KEY
        ):
            raise ValueError(
                "SECRET_KEY must be set to a unique value when VERIFYGRID_ENV=production."
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
