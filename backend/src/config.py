from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = Field(default="")
    planner_model: str = Field(default="claude-sonnet-4-6")
    classifier_model: str = Field(default="claude-haiku-4-5-20251001")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/agent_testing"
    )
    # IMPORTANT: read from config so switching embedding models isn't a table rewrite
    embedding_dim: int = Field(default=1536)

    # Object storage
    minio_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_bucket: str = Field(default="agent-testing")
    minio_secure: bool = Field(default=False)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379")

    # Langfuse
    langfuse_secret_key: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_host: str = Field(default="http://localhost:3001")

    # Parsing backend: "local" (Docling) or "cloud"
    parsing_backend: str = Field(default="local")

    # Auth session encryption (AES-256, base64-encoded 32 bytes)
    auth_session_encryption_key: str = Field(default="")

    # Confidence thresholds
    confidence_auto_approve_threshold: float = Field(default=0.85)

    # Upload endpoint had no size limit at all -- an unauthenticated-in-effect
    # (pre-finding-#1) or even authenticated caller could upload arbitrarily
    # large files, read fully into memory in upload.py, and exhaust RAM/disk.
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024)  # 50 MB

    # Per-tenant LLM cost guard (USD/day; 0 = unlimited)
    default_tenant_daily_llm_budget_usd: float = Field(default=0.0)

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4318")
    service_name: str = Field(default="agent-testing-backend")


settings = Settings()
