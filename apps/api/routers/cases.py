"""Case ingestion and listing endpoints."""

import hashlib
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.orm import Session

from apps.api.dependencies import get_session, get_settings, get_storage
from apps.api.schemas import CaseListResponse, CaseResponse
from apps.api.settings import ApiSettings
from packages.core.db.models import Case, Decision
from packages.core.db.repositories import CaseRepo
from packages.core.enums import CaseStatus, DecisionKind, DocType
from packages.core.storage import S3Storage, StorageUnavailable

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])

_MAGIC_TYPES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"%PDF-", "application/pdf", "pdf"),
)


def _detect_media(content: bytes) -> tuple[str, str] | None:
    for signature, content_type, extension in _MAGIC_TYPES:
        if content.startswith(signature):
            return content_type, extension
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff", "tiff"
    return None


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("", response_model=CaseResponse, status_code=202)
def upload_case(
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    storage: Annotated[S3Storage, Depends(get_storage)],
    channel: Annotated[str | None, Form()] = "API",
) -> CaseResponse:
    maximum_bytes = settings.max_upload_mb * 1024 * 1024
    content = file.file.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise _error(
            413, "UPLOAD_TOO_LARGE", "The uploaded file exceeds the configured size limit."
        )
    detected = _detect_media(content)
    if detected is None:
        raise _error(400, "UNSUPPORTED_MEDIA_TYPE", "Upload a JPEG, PNG, PDF, or TIFF document.")

    content_type, extension = detected
    sha256 = hashlib.sha256(content).hexdigest()
    lock_key = int.from_bytes(bytes.fromhex(sha256[:16]), byteorder="big", signed=True)
    created_at = datetime.now(UTC)
    case_response: CaseResponse
    status_code = 202

    try:
        with session.begin():
            session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
            existing = session.scalar(
                select(Case).where(Case.sha256 == sha256).order_by(Case.created_at.asc()).limit(1)
            )
            if existing is not None:
                case_response = CaseResponse.model_validate(
                    {
                        "case_id": existing.case_id,
                        "status": existing.status,
                        "duplicate_of": existing.case_id,
                        "received_at": existing.received_at,
                        "channel": existing.channel,
                        "doc_type": existing.doc_type,
                        "mime_type": existing.mime_type,
                    }
                )
                status_code = 200
            else:
                case_id = uuid4()
                object_key = f"raw/{created_at:%Y/%m}/{case_id}/original.{extension}"
                storage.put(
                    key=object_key,
                    content=content,
                    content_type=content_type,
                    sha256=sha256,
                )
                case = Case(
                    case_id=case_id,
                    status=CaseStatus.RECEIVED,
                    channel=channel,
                    object_key=object_key,
                    sha256=sha256,
                    mime_type=content_type,
                    received_at=created_at,
                )
                CaseRepo(session).add(case)
                case_response = CaseResponse.model_validate(case)
                # TODO(Step 12): enqueue the processing pipeline after the case is committed.
    except StorageUnavailable as error:
        raise _error(503, "STORAGE_UNAVAILABLE", "The document could not be stored.") from error

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content=case_response.model_dump(mode="json"),
    )


@router.get("", response_model=CaseListResponse)
def list_cases(
    session: Annotated[Session, Depends(get_session)],
    status: CaseStatus | None = None,
    decision: DecisionKind | None = None,
    doc_type: DocType | None = None,
    q: str | None = None,
    received_from: Annotated[datetime | None, Query(alias="from")] = None,
    received_to: Annotated[datetime | None, Query(alias="to")] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> CaseListResponse:
    filters = []
    if status is not None:
        filters.append(Case.status == status)
    if doc_type is not None:
        filters.append(Case.doc_type == doc_type)
    if decision is not None:
        filters.append(
            select(Decision.decision_id)
            .where(Decision.case_id == Case.case_id, Decision.decision == decision)
            .exists()
        )
    if received_from is not None:
        filters.append(Case.received_at >= received_from)
    if received_to is not None:
        filters.append(Case.received_at <= received_to)
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(cast(Case.case_id, String).ilike(pattern), Case.member_ref.ilike(pattern))
        )

    total = session.scalar(select(func.count()).select_from(Case).where(*filters)) or 0
    statement = (
        select(Case)
        .where(*filters)
        .order_by(Case.created_at.desc(), Case.case_id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return CaseListResponse(
        items=[CaseResponse.model_validate(case) for case in session.scalars(statement)],
        total=total,
    )


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> CaseResponse:
    case = CaseRepo(session).get(case_id)
    if case is None:
        raise _error(404, "CASE_NOT_FOUND", "The requested case was not found.")
    return CaseResponse.model_validate(case)
