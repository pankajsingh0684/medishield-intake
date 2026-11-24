"""HTTP response schemas for case ingestion and retrieval."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from packages.core.enums import CaseStatus, DecisionKind, DocType


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


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    pipeline_run: UUID
    agent: str
    agent_version: str
    status: str
    model: str | None
    prompt_version: str | None
    confidence: float | None
    output: dict
    error: str | None
    started_at: datetime
    finished_at: datetime


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision_id: UUID
    pipeline_run: UUID
    decision: DecisionKind
    confidence: float
    justification: str
    rule_trace: list[dict]
    config_snapshot: dict
    created_at: datetime


class OverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    override_id: UUID
    user_id: UUID
    from_decision: DecisionKind | None
    to_decision: DecisionKind
    reason: str
    created_at: datetime


class CaseDetailResponse(CaseResponse):
    agent_runs: list[AgentRunResponse]
    original_decision: DecisionResponse | None
    overrides: list[OverrideResponse]
    effective_decision: DecisionKind | None
    document_url: str


class ReviewQueueResponse(BaseModel):
    items: list[CaseDetailResponse]
    total: int


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    ts: datetime
    actor_type: str
    actor: str
    event_type: str
    payload: dict


class OverrideRequest(BaseModel):
    to_decision: DecisionKind
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("Reason must contain at least 10 non-whitespace characters")
        return normalized


class ReclassifyRequest(BaseModel):
    doc_type: DocType


class PipelineActionResponse(BaseModel):
    case_id: UUID
    pipeline_run: UUID
    status: CaseStatus


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


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
