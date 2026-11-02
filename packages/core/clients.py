"""Authenticated clients for configured infrastructure services."""

from qdrant_client import QdrantClient
from redis import Redis

from packages.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        password=settings.redis_password.get_secret_value(),
        decode_responses=True,
    )


def create_qdrant_client(settings: Settings) -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
    )
