"""Test configuration: the suite sets its own environment and never reads the repo .env."""

import os

import pytest

from apps.api.settings import ApiSettings
from packages.core.config import Settings

TEST_ENVIRONMENT = {
    "APP_ENV": "test",
    "LLM_PROVIDER": "stub",
    "LLM_FALLBACK_PROVIDER": "",
    "LLM_VISION_MODEL": "test-vision-model",
    "LLM_TEXT_MODEL": "test-text-model",
    "LLM_FALLBACK_MODEL": "test-fallback-model",
    "LLM_RECORD_FIXTURES": "false",
    "GROQ_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "OPENAI_API_KEY": "",
    "JWT_SECRET": "test-jwt-secret",
    "SEED_TEST_USER_PASSWORD": "test-seed-user-password",
    "ALLOW_RECEIVED_AT_OVERRIDE": "false",
    "NPI_LUHN_STRICT": "false",
    "LANGSMITH_ENABLED": "false",
    "LANGSMITH_API_KEY": "",
}
# Service endpoints fall back to harmless defaults; DB tests additionally need a reachable test DB.
SERVICE_DEFAULTS = {
    "DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:5432/medishield",
    "REDIS_URL": "redis://127.0.0.1:6380/0",
    "REDIS_PASSWORD": "test-redis-password",
    "S3_ENDPOINT": "http://127.0.0.1:9000",
    "S3_ACCESS_KEY": "test-access-key",
    "S3_SECRET_KEY": "test-secret-key",
    "S3_BUCKET": "medishield-documents",
    "QDRANT_URL": "http://127.0.0.1:6333",
    "QDRANT_API_KEY": "test-qdrant-key",
}

os.environ.update(TEST_ENVIRONMENT)
for _name, _value in SERVICE_DEFAULTS.items():
    os.environ.setdefault(_name, _value)

# Settings classes ignore the repo .env during tests; tests that check the default path restore it.
for _settings_class in (Settings, ApiSettings):
    _settings_class.model_config["env_file"] = None


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in TEST_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
