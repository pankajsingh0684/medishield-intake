from unittest.mock import patch

from redis.connection import parse_url

from apps.worker.celery_app import celery_app, configure_celery
from packages.core.clients import authenticated_redis_url, create_qdrant_client, create_redis_client
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
        "redis://:redis-password@127.0.0.1:6380/0",
        decode_responses=True,
    )


def test_celery_broker_url_uses_encoded_configured_password() -> None:
    dummy_password = "dummy:@/ ?#%"

    configure_celery("redis://127.0.0.1:6380/0", dummy_password)

    broker_url = celery_app.conf.broker_url
    assert broker_url == celery_app.conf.result_backend
    assert ":dummy%3A%40%2F%20%3F%23%25@" in broker_url
    assert "dummy:@/ ?#%" not in broker_url
    assert parse_url(broker_url)["password"] == dummy_password

    configure_celery("redis://127.0.0.1:6380/0", "redis-password")


def test_worker_registers_pipeline_task_on_api_queue() -> None:
    celery_app.loader.import_default_modules()

    assert "apps.worker.tasks.run_pipeline" in celery_app.tasks
    assert celery_app.conf.task_routes["apps.worker.tasks.run_pipeline"]["queue"] == "pipeline"
    assert "pipeline" in {queue.name for queue in celery_app.conf.task_queues}


def test_authenticated_redis_url_preserves_acl_username() -> None:
    url = authenticated_redis_url("redis://worker@127.0.0.1:6380/0", "dummy:@ password")

    assert parse_url(url)["username"] == "worker"
    assert parse_url(url)["password"] == "dummy:@ password"


def test_qdrant_client_uses_configured_api_key() -> None:
    settings = make_settings()

    with patch("packages.core.clients.QdrantClient") as factory:
        client = create_qdrant_client(settings)

    assert client is factory.return_value
    factory.assert_called_once_with(
        url=settings.qdrant_url,
        api_key="qdrant-api-key",
    )
