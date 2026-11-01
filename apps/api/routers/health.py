"""Liveness and dependency readiness routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.dependencies import get_session, get_storage
from packages.core.storage import S3Storage

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[S3Storage, Depends(get_storage)],
) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
        storage.check_ready()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": "A required service is unavailable.",
            },
        ) from error
    return {"status": "ready"}
