"""Case ingestion and listing endpoints."""

import hashlib
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.orm import Session

from apps.api.dependencies import current_user, get_session, get_settings, get_storage
from apps.api.schemas import (
    AuditEventResponse,
    CaseDetailResponse,
    CaseListResponse,
    CaseResponse,
    DecisionResponse,
    OverrideRequest,
    OverrideResponse,
    PipelineActionResponse,
    ReclassifyRequest,
    ReviewQueueResponse,
)
from apps.api.settings import ApiSettings
from packages.core.db.models import AgentRun, Case, Decision, Override, User
from packages.core.db.repositories import AuditRepo, CaseRepo
from packages.core.enums import CaseStatus, DecisionKind, DocType
from packages.core.storage import S3Storage, StorageUnavailable

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])
review_router = APIRouter(prefix="/api/v1", tags=["cases"])

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


def _case_detail(
    session: Session,
    case: Case,
    storage: S3Storage,
) -> CaseDetailResponse:
    runs = list(
        session.scalars(
            select(AgentRun)
            .where(AgentRun.case_id == case.case_id)
            .order_by(AgentRun.started_at.asc(), AgentRun.run_id.asc())
        )
    )
    latest_run = max(
        runs,
        key=lambda run: (run.started_at, run.run_id),
        default=None,
    )
    latest_run_id = latest_run.pipeline_run if latest_run is not None else None
    latest_runs = [run for run in runs if run.pipeline_run == latest_run_id]
    original_decision = None
    if latest_run_id is not None:
        original_decision_row = session.scalar(
            select(Decision).where(
                Decision.case_id == case.case_id,
                Decision.pipeline_run == latest_run_id,
            )
        )
        if original_decision_row is not None:
            original_decision = DecisionResponse.model_validate(original_decision_row)
    overrides = list(
        session.scalars(
            select(Override)
            .where(Override.case_id == case.case_id)
            .order_by(Override.created_at.asc(), Override.override_id.asc())
        )
    )
    latest_override = overrides[-1] if overrides else None
    effective_decision = (
        latest_override.to_decision
        if latest_override is not None
        else original_decision.decision
        if original_decision is not None
        else None
    )
    try:
        document_url = storage.generate_presigned_url(case.object_key, expires_in=600)
    except StorageUnavailable as error:
        raise _error(
            503, "STORAGE_UNAVAILABLE", "The document URL could not be generated."
        ) from error
    return CaseDetailResponse(
        **CaseResponse.model_validate(case).model_dump(),
        agent_runs=latest_runs,
        original_decision=original_decision,
        overrides=overrides,
        effective_decision=effective_decision,
        document_url=document_url,
    )


@router.post("", response_model=CaseResponse, status_code=202)
def upload_case(
    request: Request,
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
    enqueue_case_id: UUID | None = None

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
                enqueue_case_id = case_id
    except StorageUnavailable as error:
        raise _error(503, "STORAGE_UNAVAILABLE", "The document could not be stored.") from error

    if enqueue_case_id is not None:
        request.app.state.pipeline_task.apply_async(
            args=[str(enqueue_case_id), str(uuid4())],
            queue="pipeline",
        )

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


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[S3Storage, Depends(get_storage)],
) -> CaseDetailResponse:
    case = CaseRepo(session).get(case_id)
    if case is None:
        raise _error(404, "CASE_NOT_FOUND", "The requested case was not found.")
    return _case_detail(session, case, storage)


@router.get("/{case_id}/audit", response_model=list[AuditEventResponse])
def get_case_audit(
    case_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[AuditEventResponse]:
    if CaseRepo(session).get(case_id) is None:
        raise _error(404, "CASE_NOT_FOUND", "The requested case was not found.")
    return [
        AuditEventResponse.model_validate(event) for event in AuditRepo(session).for_case(case_id)
    ]


@review_router.get("/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[S3Storage, Depends(get_storage)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> ReviewQueueResponse:
    latest_decisions = select(
        Decision.case_id.label("case_id"),
        Decision.decision.label("decision"),
        func.row_number()
        .over(
            partition_by=Decision.case_id,
            order_by=(Decision.created_at.desc(), Decision.decision_id.desc()),
        )
        .label("position"),
    ).subquery()
    has_override = select(Override.override_id).where(Override.case_id == Case.case_id).exists()
    queue_filter = or_(
        Case.status.in_([CaseStatus.NEEDS_REVIEW, CaseStatus.FAILED]),
        (latest_decisions.c.position == 1)
        & (latest_decisions.c.decision == DecisionKind.ESCALATE)
        & ~has_override,
    )
    total = (
        session.scalar(
            select(func.count())
            .select_from(Case)
            .outerjoin(
                latest_decisions,
                (latest_decisions.c.case_id == Case.case_id) & (latest_decisions.c.position == 1),
            )
            .where(queue_filter)
        )
        or 0
    )
    cases = list(
        session.scalars(
            select(Case)
            .outerjoin(
                latest_decisions,
                (latest_decisions.c.case_id == Case.case_id) & (latest_decisions.c.position == 1),
            )
            .where(queue_filter)
            .order_by(Case.created_at.desc(), Case.case_id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return ReviewQueueResponse(
        items=[_case_detail(session, case, storage) for case in cases],
        total=total,
    )


@router.post("/{case_id}/override", response_model=OverrideResponse)
def override_case(
    case_id: UUID,
    payload: OverrideRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> OverrideResponse:
    with session.begin():
        case = CaseRepo(session).get(case_id)
        if case is None:
            raise _error(404, "CASE_NOT_FOUND", "The requested case was not found.")
        latest_decision = session.scalar(
            select(Decision)
            .where(Decision.case_id == case_id)
            .order_by(Decision.created_at.desc(), Decision.decision_id.desc())
        )
        if latest_decision is None:
            raise _error(409, "DECISION_NOT_AVAILABLE", "A decision is required before override.")
        override = Override(
            case_id=case_id,
            user_id=user.user_id,
            from_decision=latest_decision.decision,
            to_decision=payload.to_decision,
            reason=payload.reason,
        )
        session.add(override)
        session.flush()
        case.status = CaseStatus.OVERRIDDEN
        AuditRepo(session).append(
            case_id=case_id,
            actor_type="USER",
            actor=str(user.user_id),
            event_type="OVERRIDE",
            payload={
                "override_id": str(override.override_id),
                "from_decision": latest_decision.decision.value,
                "to_decision": payload.to_decision.value,
                "reason": payload.reason,
            },
        )
        response = OverrideResponse.model_validate(override)
    return response


@router.post("/{case_id}/rerun", response_model=PipelineActionResponse, status_code=202)
def rerun_case(
    case_id: UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PipelineActionResponse:
    with session.begin():
        case = CaseRepo(session).get(case_id)
        if case is None:
            raise _error(404, "CASE_NOT_FOUND", "The requested case was not found.")
        if case.status in {
            CaseStatus.RECEIVED,
            CaseStatus.CLASSIFIED,
            CaseStatus.PROCESSING,
            CaseStatus.FRAUD_CHECK,
            CaseStatus.AGGREGATED,
        }:
            raise _error(409, "CASE_PROCESSING", "The case is still processing.")
        pipeline_run = uuid4()
        AuditRepo(session).append(
            case_id=case_id,
            actor_type="USER",
            actor=str(user.user_id),
            event_type="RERUN",
            payload={"pipeline_run": str(pipeline_run)},
        )
    request.app.state.pipeline_task.apply_async(
        args=[str(case_id), str(pipeline_run)], queue="pipeline"
    )
    return PipelineActionResponse(
        case_id=case_id, pipeline_run=pipeline_run, status=CaseStatus.RECEIVED
    )


@router.post("/{case_id}/reclassify", response_model=PipelineActionResponse, status_code=202)
def reclassify_case(
    case_id: UUID,
    payload: ReclassifyRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PipelineActionResponse:
    with session.begin():
        case = CaseRepo(session).get(case_id)
        if case is None:
            raise _error(404, "CASE_NOT_FOUND", "The requested case was not found.")
        if case.status in {
            CaseStatus.RECEIVED,
            CaseStatus.CLASSIFIED,
            CaseStatus.PROCESSING,
            CaseStatus.FRAUD_CHECK,
            CaseStatus.AGGREGATED,
        }:
            raise _error(409, "CASE_PROCESSING", "The case is still processing.")
        old_doc_type = case.doc_type
        pipeline_run = uuid4()
        AuditRepo(session).append(
            case_id=case_id,
            actor_type="USER",
            actor=str(user.user_id),
            event_type="RECLASSIFY",
            payload={
                "old_doc_type": old_doc_type.value if old_doc_type else None,
                "new_doc_type": payload.doc_type.value,
                "pipeline_run": str(pipeline_run),
            },
        )
    request.app.state.pipeline_task.apply_async(
        args=[str(case_id), str(pipeline_run)],
        kwargs={"fixed_doc_type": payload.doc_type.value},
        queue="pipeline",
    )
    return PipelineActionResponse(
        case_id=case_id, pipeline_run=pipeline_run, status=CaseStatus.RECEIVED
    )
