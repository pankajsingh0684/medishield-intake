"""Configuration limited to resources used by the ingestion API."""

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.engine import make_url

from packages.core.config import EnvFileSettings, reject_production_placeholders


class ApiSettings(EnvFileSettings):
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
    jwt_secret: SecretStr
    seed_test_user_password: SecretStr
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    langsmith_api_key: SecretStr | None = None
    max_upload_mb: int = Field(default=25, gt=0)

    @model_validator(mode="after")
    def reject_production_placeholders(self) -> "ApiSettings":
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
