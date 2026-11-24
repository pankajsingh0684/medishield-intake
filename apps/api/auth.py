"""Short-lived JWT authentication and login throttling for the local API."""

import base64
import binascii
import hashlib
import hmac
import json
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.settings import ApiSettings
from packages.core.db.models import User
from packages.core.enums import UserRole

_bearer = HTTPBearer(auto_error=False)
_password_hasher = PasswordHasher()
_rate_lock = threading.Lock()
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_upload_attempts: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_LIMIT = 5
_LOGIN_WINDOW_SECONDS = 60
_UPLOAD_LIMIT = 30
_UPLOAD_WINDOW_SECONDS = 60


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "UNAUTHORIZED", "message": "Valid authentication is required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _b64encode(decoded) != value:
        raise ValueError("Noncanonical JWT segment")
    return decoded


def create_access_token(user: User, settings: ApiSettings, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user.user_id),
        "role": user.role.value,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.jwt_ttl_min)).timestamp()),
    }
    header = _b64encode(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{body}".encode("ascii")
    signature = hmac.new(
        settings.jwt_secret.get_secret_value().encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{header}.{body}.{_b64encode(signature)}"


def decode_access_token(
    token: str, settings: ApiSettings, *, now: datetime | None = None
) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected = hmac.new(
            settings.jwt_secret.get_secret_value().encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_segment)):
            raise _unauthorized()
        header = json.loads(_b64decode(header_segment))
        payload = json.loads(_b64decode(payload_segment))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise _unauthorized()
        expires_at = datetime.fromtimestamp(int(payload["exp"]), UTC)
        if expires_at <= (now or datetime.now(UTC)):
            raise _unauthorized()
        UUID(payload["sub"])
        UserRole(payload["role"])
        return payload
    except HTTPException:
        raise
    except (
        binascii.Error,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as error:
        raise _unauthorized() from error


def _authenticated_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()
    settings: ApiSettings = request.app.state.settings
    claims = decode_access_token(credentials.credentials, settings)
    user_id = UUID(claims["sub"])
    with Session(request.app.state.engine) as session:
        user = session.get(User, user_id)
        if user is None or user.role.value != claims["role"]:
            raise _unauthorized()
        session.expunge(user)
        return user


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    settings: ApiSettings = request.app.state.settings
    if (
        credentials is not None
        and settings.service_token is not None
        and hmac.compare_digest(
            credentials.credentials.encode("utf-8"),
            settings.service_token.get_secret_value().encode("utf-8"),
        )
    ):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Service token is upload-only."},
        )
    return _authenticated_user(request, credentials)


def require_role(*allowed_roles: UserRole) -> Callable[..., User]:
    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "This role cannot access the resource."},
            )
        return user

    return dependency


def require_upload_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    settings: ApiSettings = request.app.state.settings
    service_token = settings.service_token
    if credentials is not None and service_token is not None:
        provided = credentials.credentials.encode("utf-8")
        expected = service_token.get_secret_value().encode("utf-8")
        if credentials.scheme.casefold() == "bearer" and hmac.compare_digest(provided, expected):
            return None
    user = _authenticated_user(request, credentials)
    if user.role not in {UserRole.REVIEWER, UserRole.SUPERVISOR, UserRole.ADMIN}:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "This role cannot upload cases."},
        )
    return user


def enforce_upload_rate_limit(
    request: Request, *, clock: Callable[[], float] = time.monotonic
) -> None:
    key = request.client.host if request.client else "unknown"
    current_time = clock()
    with _rate_lock:
        attempts = _upload_attempts[key]
        while attempts and attempts[0] <= current_time - _UPLOAD_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _UPLOAD_LIMIT:
            raise HTTPException(
                status_code=429,
                detail={"code": "UPLOAD_RATE_LIMITED", "message": "Too many uploads."},
                headers={"Retry-After": str(_UPLOAD_WINDOW_SECONDS)},
            )
        attempts.append(current_time)


def authenticate_login(
    email: str,
    password: str,
    request: Request,
    session: Session,
    settings: ApiSettings,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    client_ip = request.client.host if request.client else "unknown"
    normalized_email = email.strip().casefold()
    keys = (f"ip:{client_ip}", f"username:{normalized_email}")
    current_time = clock()
    with _rate_lock:
        attempts_by_key = [_login_attempts[key] for key in keys]
        for attempts in attempts_by_key:
            while attempts and attempts[0] <= current_time - _LOGIN_WINDOW_SECONDS:
                attempts.popleft()
        if any(len(attempts) >= _LOGIN_LIMIT for attempts in attempts_by_key):
            raise HTTPException(
                status_code=429,
                detail={"code": "LOGIN_RATE_LIMITED", "message": "Too many login attempts."},
                headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)},
            )
        for attempts in attempts_by_key:
            attempts.append(current_time)

    user = session.scalar(select(User).where(User.email == normalized_email))
    valid = False
    if user is not None:
        try:
            valid = _password_hasher.verify(user.password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
    if not valid:
        raise _unauthorized()

    with _rate_lock:
        for key in keys:
            _login_attempts.pop(key, None)
    return create_access_token(user, settings)


def reset_login_rate_limits() -> None:
    """Clear process-local throttles, primarily for isolated tests."""
    with _rate_lock:
        _login_attempts.clear()


def reset_upload_rate_limits() -> None:
    with _rate_lock:
        _upload_attempts.clear()
