"""Authenticated clients for configured infrastructure services."""

from urllib.parse import quote

from qdrant_client import QdrantClient
from redis import Redis
from sqlalchemy.engine import make_url

from packages.core.config import Settings


def authenticated_redis_url(redis_url: str, redis_password: str) -> str:
    """Return a Redis URL with the configured password safely URL-encoded."""
    parsed_url = make_url(redis_url)
    base_url = parsed_url.set(username="", password="").render_as_string(hide_password=False)
    username = quote(parsed_url.username, safe="") if parsed_url.username else ""
    password = quote(redis_password, safe="")
    auth = f"{username}:{password}" if username else f":{password}"
    scheme, remainder = base_url.split("://", maxsplit=1)
    if not remainder.startswith(":@"):
        raise ValueError("Could not safely replace Redis URL credentials")
    remainder = remainder[2:]
    return f"{scheme}://{auth}@{remainder}"


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(
        authenticated_redis_url(settings.redis_url, settings.redis_password.get_secret_value()),
        decode_responses=True,
    )


def create_qdrant_client(settings: Settings) -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
    )
