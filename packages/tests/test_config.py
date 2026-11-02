import pytest
from pydantic import ValidationError

from packages.core.config import Settings

REQUIRED_ENVIRONMENT = {
    "DATABASE_URL": "postgresql://user:password@localhost:5432/medishield",
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_PASSWORD": "test-redis-password",
    "S3_ENDPOINT": "http://localhost:9000",
    "S3_ACCESS_KEY": "test-access-key",
    "S3_SECRET_KEY": "test-secret-key",
    "S3_BUCKET": "test-bucket",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_API_KEY": "test-qdrant-key",
    "LLM_VISION_MODEL": "test-vision-model",
    "LLM_TEXT_MODEL": "test-text-model",
    "LLM_FALLBACK_MODEL": "test-fallback-model",
    "JWT_SECRET": "test-jwt-secret",
    "SEED_TEST_USER_PASSWORD": "test-seed-user-password",
}


def set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    settings = Settings(_env_file=None)

    assert settings.database_url == REQUIRED_ENVIRONMENT["DATABASE_URL"]
    assert settings.s3_access_key.get_secret_value() == "test-access-key"
    assert settings.llm_provider == "openai"


def test_missing_required_settings_raise_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    message = str(error.value)
    assert "database_url" in message
    assert "redis_password" in message
    assert "qdrant_api_key" in message


def test_documented_threshold_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    for name in (
        "LLM_PROVIDER",
        "THRESH_FRAUD_ESCALATE",
        "THRESH_FRAUD_HIGH",
        "THRESH_AGENT_CONFIDENCE",
        "THRESH_CLASSIFY_REVIEW",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "stub"
    assert settings.llm_fallback_provider is None
    assert settings.threshold_fraud_escalate == 0.30
    assert settings.threshold_fraud_high == 0.60
    assert settings.threshold_agent_confidence == 0.60
    assert settings.threshold_classify_review == 0.60


def test_step_5b_setting_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    for name in (
        "APP_ENV",
        "NPI_LUHN_STRICT",
        "ALLOW_RECEIVED_AT_OVERRIDE",
        "NEAR_THRESHOLD_LOW",
        "NEAR_THRESHOLD_HIGH",
        "DATE_CONFLICT_DAYS",
        "READMISSION_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.npi_luhn_strict is False
    assert settings.allow_received_at_override is False
    assert settings.near_threshold_low == 9500
    assert settings.near_threshold_high == 10000
    assert settings.date_conflict_days == 30
    assert settings.readmission_days == 30


def test_received_at_override_allowed_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)

    settings = Settings(
        _env_file=None,
        app_env="test",
        allow_received_at_override=True,
    )

    assert settings.allow_received_at_override is True


def test_received_at_override_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)

    with pytest.raises(ValidationError, match="cannot be enabled in production"):
        Settings(
            _env_file=None,
            app_env="production",
            allow_received_at_override=True,
        )


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_placeholder_secrets_are_allowed_outside_production(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "replace-with-local-only-secret")

    settings = Settings(_env_file=None, app_env=app_env)

    assert settings.app_env == app_env


def test_placeholder_secret_is_rejected_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "replace-with-local-only-secret")

    with pytest.raises(ValidationError, match="must not use replace-with placeholders"):
        Settings(_env_file=None, app_env="production")
