"""HTTP response schemas for case ingestion and retrieval."""

from datetime import datetime
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
