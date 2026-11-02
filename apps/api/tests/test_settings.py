import pytest
from pydantic import ValidationError

from apps.api.settings import ApiSettings
from packages.core.config import Settings
from packages.core.db.session import DatabaseSettings


def test_api_settings_ignore_test_database_and_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    development_database_url = "postgresql://user:password@localhost:5432/medishield"
    development_bucket = "medishield-documents"
    monkeypatch.setenv("DATABASE_URL", development_database_url)
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql://user:password@localhost:5432/medishield_test"
    )
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6380/0")
    monkeypatch.setenv("REDIS_PASSWORD", "test-redis-password")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("S3_BUCKET", development_bucket)
    monkeypatch.setenv("S3_TEST_BUCKET", "medishield-documents-test")
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("SEED_TEST_USER_PASSWORD", "test-seed-password")

    settings = ApiSettings(_env_file=None)

    assert settings.database_url == development_database_url
    assert settings.s3_bucket == development_bucket
    assert "s3_test_bucket" not in ApiSettings.model_fields


def test_core_and_api_settings_require_dotenv_with_setup_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    for settings_type in (Settings, ApiSettings, DatabaseSettings):
        with pytest.raises(RuntimeError, match="Copy .env.example to .env"):
            settings_type()


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_api_accepts_placeholder_secrets_outside_production(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:replace-with-db@localhost/medishield")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/0")
    monkeypatch.setenv("REDIS_PASSWORD", "replace-with-redis")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "medishield-local")
    monkeypatch.setenv("S3_SECRET_KEY", "replace-with-s3")
    monkeypatch.setenv("S3_BUCKET", "medishield-documents")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "replace-with-qdrant")
    monkeypatch.setenv("JWT_SECRET", "replace-with-jwt")
    monkeypatch.setenv("SEED_TEST_USER_PASSWORD", "replace-with-seed")

    assert ApiSettings(_env_file=None).app_env == app_env


def test_api_rejects_placeholder_secrets_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:replace-with-db@localhost/medishield")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/0")
    monkeypatch.setenv("REDIS_PASSWORD", "actual-redis-password")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "medishield-local")
    monkeypatch.setenv("S3_SECRET_KEY", "actual-s3-secret")
    monkeypatch.setenv("S3_BUCKET", "medishield-documents")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "actual-qdrant-key")
    monkeypatch.setenv("JWT_SECRET", "replace-with-jwt")
    monkeypatch.setenv("SEED_TEST_USER_PASSWORD", "actual-seed-password")

    with pytest.raises(ValidationError, match="must not use replace-with placeholders"):
        ApiSettings(_env_file=None)
