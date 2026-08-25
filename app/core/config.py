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
    minio_public_secure: bool = False
    minio_region: str = "us-east-1"

    attachment_max_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    attachment_url_expire_minutes: int = Field(default=15, gt=0, le=60)
    attachment_processing_max_attempts: int = Field(default=5, gt=0, le=20)
    export_url_expire_minutes: int = Field(default=15, gt=0, le=60)
    export_processing_max_attempts: int = Field(default=5, gt=0, le=20)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "forkroom-api"
    otel_trace_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

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
    meeting_token_expire_minutes: int = Field(default=5, gt=0, le=15)
    meeting_websocket_url: str = "ws://localhost:8000/api/v1/ws/meetings"
    meeting_allowed_origins: list[str] = ["http://localhost:3000"]
    meeting_presence_ttl_seconds: int = Field(default=60, ge=15, le=300)
    meeting_max_participants: int = Field(default=4, ge=2, le=4)
    meeting_max_timer_seconds: int = Field(default=7200, ge=60, le=86400)
    turn_urls: list[str] = [
        "stun:localhost:3478",
        "turn:localhost:3478?transport=udp",
        "turn:localhost:3478?transport=tcp",
    ]
    turn_shared_secret: str = Field(
        default="development-turn-secret-change-me",
        min_length=16,
    )
    turn_credential_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    frontend_url: str = "http://localhost:3000"
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    google_oauth_scopes: str = "openid email profile"
    google_oauth_state_ttl_seconds: int = Field(default=600, ge=300, le=1800)
    google_oauth_http_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_signing_secret: str | None = None
    slack_redirect_uri: str | None = None
    slack_bot_scopes: str = "chat:write,channels:read,groups:read"
    integration_token_encryption_key: str | None = None
    integration_oauth_state_ttl_seconds: int = Field(default=600, ge=300, le=1800)
    integration_http_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    integration_max_retries: int = Field(default=6, ge=1, le=12)
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
