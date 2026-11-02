"""Environment-backed application settings."""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


def reject_production_placeholders(app_env: str, secrets: dict[str, str | None]) -> None:
    if app_env != "production":
        return
    placeholders = [
        name
        for name, value in secrets.items()
        if value is not None and value.casefold().startswith("replace-with")
    ]
    if placeholders:
        names = ", ".join(placeholders)
        raise ValueError(f"Production secrets must not use replace-with placeholders: {names}")


class EnvFileSettings(BaseSettings):
    def __init__(self, **values: Any) -> None:
        configured_files = values.get("_env_file", self.model_config.get("env_file"))
        if configured_files is not None:
            paths = (
                (configured_files,)
                if isinstance(configured_files, (str, Path))
                else tuple(configured_files)
            )
            requires_dotenv = any(Path(path).name == ".env" for path in paths)
            if requires_dotenv and not Path(".env").is_file():
                raise RuntimeError("Missing .env. Copy .env.example to .env before startup.")
        super().__init__(**values)


class Settings(EnvFileSettings):
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
    redis_password: SecretStr
    s3_endpoint: str
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket: str
    qdrant_url: str
    qdrant_api_key: SecretStr

    llm_provider: Literal["stub", "groq", "anthropic", "openai"] = "stub"
    llm_vision_model: str
    llm_text_model: str
    llm_fallback_provider: Literal["groq", "anthropic", "openai"] | None = None
    llm_fallback_model: str
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_record_fixtures: bool = False
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
    seed_test_user_password: SecretStr
    jwt_ttl_min: int = Field(default=60, gt=0)
    langsmith_enabled: bool = False
    langsmith_api_key: SecretStr | None = None
    phi_log_redaction: bool = True

    @model_validator(mode="after")
    def reject_production_clock_override(self) -> "Settings":
        if self.app_env == "production" and self.allow_received_at_override:
            raise ValueError("ALLOW_RECEIVED_AT_OVERRIDE cannot be enabled in production")
        database_password = make_url(self.database_url).password
        reject_production_placeholders(
            self.app_env,
            {
                "DATABASE_URL password": database_password,
                "REDIS_PASSWORD": self.redis_password.get_secret_value(),
                "S3_SECRET_KEY": self.s3_secret_key.get_secret_value(),
                "QDRANT_API_KEY": self.qdrant_api_key.get_secret_value(),
                "GROQ_API_KEY": self.groq_api_key.get_secret_value() if self.groq_api_key else None,
                "ANTHROPIC_API_KEY": self.anthropic_api_key.get_secret_value()
                if self.anthropic_api_key
                else None,
                "OPENAI_API_KEY": self.openai_api_key.get_secret_value()
                if self.openai_api_key
                else None,
                "JWT_SECRET": self.jwt_secret.get_secret_value(),
                "SEED_TEST_USER_PASSWORD": self.seed_test_user_password.get_secret_value(),
                "LANGSMITH_API_KEY": self.langsmith_api_key.get_secret_value()
                if self.langsmith_api_key
                else None,
            },
        )
        return self
