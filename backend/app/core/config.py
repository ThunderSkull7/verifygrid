from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VerifyGrid"
    app_version: str = "0.1.0"
    debug: bool = True

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
    secret_key: str = "verifygrid-default-insecure-secret-key-change-in-production-12345"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
