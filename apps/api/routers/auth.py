"""Local email/password login endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from apps.api.auth import authenticate_login
from apps.api.dependencies import get_session, get_settings
from apps.api.schemas import LoginRequest, LoginResponse
from apps.api.settings import ApiSettings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
) -> LoginResponse:
    token = authenticate_login(payload.email, payload.password, request, session, settings)
    return LoginResponse(access_token=token, expires_in=settings.jwt_ttl_min * 60)
