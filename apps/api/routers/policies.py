"""Policy PDF ingestion and policy metadata endpoints."""

import hashlib
from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.dependencies import get_session, get_settings, get_storage
from apps.api.schemas import PolicyListResponse, PolicyResponse
from apps.api.settings import ApiSettings
from packages.core.db.models import Policy
from packages.core.storage import S3Storage, StorageUnavailable
from packages.rag.ingest import infer_plan_code

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


@router.post("", response_model=PolicyResponse, status_code=202)
def upload_policy(
    request: Request,
    file: Annotated[UploadFile, File()],
    version: Annotated[str, Form(min_length=1)],
    effective_from: Annotated[date, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    storage: Annotated[S3Storage, Depends(get_storage)],
    effective_to: Annotated[date | None, Form()] = None,
) -> PolicyResponse:
    content = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Policy PDF exceeds the upload limit")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Upload a PDF policy document")
    if effective_to is not None and effective_to < effective_from:
        raise HTTPException(status_code=422, detail="effective_to must not precede effective_from")
    try:
        plan_code = infer_plan_code(file.filename or "")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    policy_id = uuid5(NAMESPACE_URL, f"medishield:plan:{plan_code}:{version}")
    object_key = (
        f"policies/{plan_code.casefold()}/{version}/{Path(file.filename or 'policy.pdf').name}"
    )
    try:
        storage.put(
            key=object_key,
            content=content,
            content_type="application/pdf",
            sha256=hashlib.sha256(content).hexdigest(),
        )
    except StorageUnavailable as error:
        raise HTTPException(status_code=503, detail="Policy could not be stored") from error

    policy = session.get(Policy, policy_id)
    if policy is None:
        policy = Policy(policy_id=policy_id)
        session.add(policy)
    policy.plan_code = plan_code
    policy.name = f"MediShield {plan_code.title()} Plan"
    policy.version = version
    policy.effective_from = effective_from
    policy.effective_to = effective_to
    policy.object_key = object_key
    policy.ingest_status = "PENDING"
    policy.chunk_count = 0
    session.commit()
    request.app.state.policy_task.apply_async(args=[str(policy_id)], queue="policy_ingest")
    return PolicyResponse.model_validate(policy)


@router.get("", response_model=PolicyListResponse)
def list_policies(
    session: Annotated[Session, Depends(get_session)],
) -> PolicyListResponse:
    items = list(session.scalars(select(Policy).order_by(Policy.plan_code, Policy.version)))
    return PolicyListResponse(items=items, total=len(items))
