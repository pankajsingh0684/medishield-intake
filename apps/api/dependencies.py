"""FastAPI dependencies for request-scoped database and storage access."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from apps.api.settings import ApiSettings
from packages.core.storage import S3Storage


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_storage(request: Request) -> S3Storage:
    return request.app.state.storage
