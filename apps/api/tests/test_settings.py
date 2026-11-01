import pytest

from apps.api.settings import ApiSettings


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
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("S3_BUCKET", development_bucket)
    monkeypatch.setenv("S3_TEST_BUCKET", "medishield-documents-test")

    settings = ApiSettings(_env_file=None)

    assert settings.database_url == development_database_url
    assert settings.s3_bucket == development_bucket
    assert "s3_test_bucket" not in ApiSettings.model_fields
