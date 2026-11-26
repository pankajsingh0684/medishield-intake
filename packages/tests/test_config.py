import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.core.config import DEFAULT_ENV_FILE, Settings

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
    "TESSERACT_CMD": "C:/tools/tesseract.exe",
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
    assert settings.tesseract_cmd == "C:/tools/tesseract.exe"


def test_default_env_file_is_repo_root_absolute_and_cwd_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected_env_file = Path(__file__).resolve().parents[2] / ".env"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(Settings.model_config, "env_file", DEFAULT_ENV_FILE)

    configured_env_file = Path(Settings.model_config["env_file"])

    assert configured_env_file == expected_env_file
    assert configured_env_file.is_absolute()
    assert DEFAULT_ENV_FILE == configured_env_file


def test_runtime_code_does_not_load_env_example_into_process_environment() -> None:
    root = Path(__file__).resolve().parents[2]
    loader_names = {"load_dotenv", "dotenv_values", "read_dotenv"}
    violations: list[str] = []

    for source_root in (root / "apps", root / "packages", root / "scripts"):
        for source_path in source_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else ""
                )
                if function_name not in loader_names:
                    continue
                arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
                uses_example = any(
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and ".env.example" in value.value
                    for argument in arguments
                    for value in ast.walk(argument)
                )
                if uses_example:
                    violations.append(f"{source_path.relative_to(root)}:{node.lineno}")

    assert not violations, "Runtime code must not load .env.example: " + ", ".join(violations)


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
        "LLM_FALLBACK_PROVIDER",
        "THRESH_FRAUD_ESCALATE",
        "THRESH_FRAUD_HIGH",
        "THRESH_AGENT_CONFIDENCE",
        "THRESH_CLASSIFY_REVIEW",
        "GROQ_RPM_LIMIT",
        "GROQ_TPM_LIMIT",
        "GROQ_TPD_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "stub"
    assert settings.llm_fallback_provider is None
    assert settings.threshold_fraud_escalate == 0.30
    assert settings.threshold_fraud_high == 0.60
    assert settings.threshold_agent_confidence == 0.60
    assert settings.threshold_classify_review == 0.60
    assert settings.groq_rpm_limit == 30
    assert settings.groq_tpm_limit == 8_000
    assert settings.groq_tpd_limit == 200_000


def test_step_5b_setting_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    for name in (
        "APP_ENV",
        "NPI_LUHN_STRICT",
        "CLAIM_AMOUNT_MAX",
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
    assert settings.claim_amount_max == 1_000_000
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


@pytest.mark.parametrize("model_field", ["LLM_TEXT_MODEL", "LLM_VISION_MODEL"])
@pytest.mark.parametrize("model_value", ["", "replace-with-model-id"])
def test_non_stub_provider_rejects_missing_or_placeholder_models(
    monkeypatch: pytest.MonkeyPatch, model_field: str, model_value: str
) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv(model_field, model_value)

    with pytest.raises(ValidationError, match="requires configured model IDs") as error:
        Settings(_env_file=None)
    assert model_field in str(error.value)


def test_stub_provider_allows_placeholder_model_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LLM_TEXT_MODEL", "replace-with-model-id")
    monkeypatch.setenv("LLM_VISION_MODEL", "replace-with-model-id")

    settings = Settings(_env_file=None)

    assert settings.llm_text_model == "replace-with-model-id"
    assert settings.llm_vision_model == "replace-with-model-id"


def test_llm_debug_raw_is_disabled_by_default_and_rejected_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.delenv("LLM_DEBUG_RAW", raising=False)
    assert Settings(_env_file=None).llm_debug_raw is False

    monkeypatch.setenv("LLM_DEBUG_RAW", "true")
    with pytest.raises(ValidationError, match="LLM_DEBUG_RAW cannot be enabled in production"):
        Settings(_env_file=None, app_env="production")
