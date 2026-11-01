"""Environment-backed application settings."""

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"

    database_url: str
    redis_url: str
    s3_endpoint: str
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket: str
    qdrant_url: str
    qdrant_api_key: SecretStr

    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_vision_model: str
    llm_text_model: str
    llm_fallback_provider: Literal["anthropic", "openai"] = "openai"
    llm_fallback_model: str
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    threshold_fraud_escalate: float = Field(default=0.30, ge=0.0, le=1.0)
    threshold_fraud_high: float = Field(default=0.60, ge=0.0, le=1.0)
    threshold_agent_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    threshold_classify_review: float = Field(default=0.60, ge=0.0, le=1.0)
    npi_luhn_strict: bool = False
    allow_received_at_override: bool = False
    near_threshold_low: int = Field(default=9500, ge=0)
    near_threshold_high: int = Field(default=10000, ge=0)
    date_conflict_days: int = Field(default=30, gt=0)
    readmission_days: int = Field(default=30, gt=0)
    max_upload_mb: int = Field(default=25, gt=0)
    pipeline_timeout_s: int = Field(default=300, gt=0)
    agent_timeout_s: int = Field(default=90, gt=0)

    jwt_secret: SecretStr
    jwt_ttl_min: int = Field(default=60, gt=0)
    langsmith_enabled: bool = False
    langsmith_api_key: SecretStr | None = None
    phi_log_redaction: bool = True

    @model_validator(mode="after")
    def reject_production_clock_override(self) -> "Settings":
        if self.app_env == "production" and self.allow_received_at_override:
            raise ValueError("ALLOW_RECEIVED_AT_OVERRIDE cannot be enabled in production")
        return self
