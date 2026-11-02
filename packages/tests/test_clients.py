from unittest.mock import patch

from packages.core.clients import create_qdrant_client, create_redis_client
from packages.core.config import Settings


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://user:db-password@127.0.0.1:5432/medishield",
        redis_url="redis://127.0.0.1:6380/0",
        redis_password="redis-password",
        s3_endpoint="http://127.0.0.1:9000",
        s3_access_key="medishield-local",
        s3_secret_key="s3-secret",
        s3_bucket="medishield-documents",
        qdrant_url="http://127.0.0.1:6333",
        qdrant_api_key="qdrant-api-key",
        llm_vision_model="vision-model",
        llm_text_model="text-model",
        llm_fallback_model="fallback-model",
        jwt_secret="jwt-secret",
        seed_test_user_password="seed-password",
    )


def test_redis_client_uses_configured_password() -> None:
    settings = make_settings()

    with patch("packages.core.clients.Redis.from_url") as factory:
        client = create_redis_client(settings)

    assert client is factory.return_value
    factory.assert_called_once_with(
        settings.redis_url,
        password="redis-password",
        decode_responses=True,
    )


def test_qdrant_client_uses_configured_api_key() -> None:
    settings = make_settings()

    with patch("packages.core.clients.QdrantClient") as factory:
        client = create_qdrant_client(settings)

    assert client is factory.return_value
    factory.assert_called_once_with(
        url=settings.qdrant_url,
        api_key="qdrant-api-key",
    )
