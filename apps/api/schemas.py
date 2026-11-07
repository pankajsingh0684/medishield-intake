"""HTTP response schemas for case ingestion and retrieval."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.core.enums import CaseStatus, DocType


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: UUID
    status: CaseStatus
    duplicate_of: UUID | None
    received_at: datetime
    channel: str | None
    doc_type: DocType | None
    mime_type: str


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: UUID
    plan_code: str | None
    name: str | None
    version: str | None
    effective_from: date | None
    effective_to: date | None
    ingest_status: str | None
    chunk_count: int | None


class PolicyListResponse(BaseModel):
    items: list[PolicyResponse]
    total: int
