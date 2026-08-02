from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ForkRoom API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://forkroom:forkroom@localhost:5432/forkroom"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "amqp://forkroom:forkroom@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"
    reminder_window_minutes: int = Field(default=60, gt=0, le=1440)
    notification_max_delivery_attempts: int = Field(default=5, gt=0, le=20)
    notification_retry_base_seconds: int = Field(default=30, gt=0, le=3600)
    notification_retry_max_seconds: int = Field(default=3600, gt=0, le=86400)
    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = "localhost:9000"
    minio_access_key: str = "forkroom"
    minio_secret_key: str = "forkroom-development-secret"
    minio_bucket: str = "forkroom-attachments"
    minio_secure: bool = False
    attachment_max_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    attachment_url_expire_minutes: int = Field(default=15, gt=0, le=60)
    attachment_processing_max_attempts: int = Field(default=5, gt=0, le=20)
    export_url_expire_minutes: int = Field(default=15, gt=0, le=60)
    export_processing_max_attempts: int = Field(default=5, gt=0, le=20)
    cors_origins: list[str] = ["http://localhost:3000"]

    jwt_access_secret: str = Field(
        default="development-access-secret-change-me-32",
        min_length=32,
    )
    jwt_refresh_secret: str = Field(
        default="development-refresh-secret-change-me-32",
        min_length=32,
    )
    jwt_collaboration_secret: str = Field(
        default="development-collaboration-secret-32",
        min_length=32,
    )
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)
    collaboration_token_expire_minutes: int = Field(default=5, gt=0, le=15)
    collaboration_url: str = "ws://localhost:1234"

    frontend_url: str = "http://localhost:3000"
    mail_from_address: str = "noreply@forkroom.local"
    mail_from_name: str = "ForkRoom"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, gt=0, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    email_verification_expire_minutes: int = Field(default=60, gt=0)
    password_reset_expire_minutes: int = Field(default=15, gt=0)

    auth_rate_limit_window_seconds: int = Field(default=60, gt=0)
    register_rate_limit_requests: int = Field(default=3, gt=0)
    login_rate_limit_requests: int = Field(default=5, gt=0)
    refresh_rate_limit_requests: int = Field(default=10, gt=0)
    logout_rate_limit_requests: int = Field(default=10, gt=0)
    verification_rate_limit_requests: int = Field(default=3, gt=0)
    forgot_password_rate_limit_requests: int = Field(default=3, gt=0)
    reset_password_rate_limit_requests: int = Field(default=5, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
