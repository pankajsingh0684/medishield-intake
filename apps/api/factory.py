"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.engine import create_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.routers.cases import router as cases_router
from apps.api.routers.health import router as health_router
from apps.api.settings import ApiSettings
from packages.core.storage import S3Storage


def create_app(
    settings: ApiSettings | None = None,
    *,
    engine: Engine | None = None,
    storage: S3Storage | None = None,
) -> FastAPI:
    api_settings = settings or ApiSettings()
    owns_engine = engine is None
    owns_storage = storage is None
    db_engine = engine or create_engine(api_settings.database_url, pool_pre_ping=True)
    object_storage = storage or S3Storage(
        endpoint_url=api_settings.s3_endpoint,
        access_key=api_settings.s3_access_key.get_secret_value(),
        secret_key=api_settings.s3_secret_key.get_secret_value(),
        bucket=api_settings.s3_bucket,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_engine:
            db_engine.dispose()
        if owns_storage:
            object_storage.close()

    app = FastAPI(title="MediShield Intake API", version="0.1.0", lifespan=lifespan)
    app.state.settings = api_settings
    app.state.engine = db_engine
    app.state.storage = object_storage
    app.include_router(health_router)
    app.include_router(cases_router)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
        detail = error.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            code, message = detail["code"], detail["message"]
        else:
            code, message = "HTTP_ERROR", str(detail)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", "unknown"),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, _: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The request parameters are invalid.",
                    "request_id": getattr(request.state, "request_id", "unknown"),
                }
            },
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, _: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "The request could not be completed.",
                    "request_id": getattr(request.state, "request_id", "unknown"),
                }
            },
        )

    return app
