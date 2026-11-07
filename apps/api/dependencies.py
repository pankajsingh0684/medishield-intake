"""FastAPI dependencies for request-scoped database and storage access."""

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.settings import ApiSettings
from packages.core.db.models import User
from packages.core.storage import S3Storage


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_storage(request: Request) -> S3Storage:
    return request.app.state.storage


def current_user(request: Request) -> User:
    with Session(request.app.state.engine) as session:
        user = session.scalar(select(User).where(User.email == "reviewer@medishield.test"))
        if user is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "REVIEWER_NOT_SEEDED", "message": "Seed the local reviewer user."},
            )
        session.expunge(user)
        return user
