"""Strict Pydantic contracts shared between MediShield agents and the graph."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from packages.core.enums import AgentStatus, DecisionKind, DocType, RiskLevel

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Score = Annotated[float, Field(ge=0.0, le=1.0)]
CoveragePercentage = Annotated[float, Field(ge=0.0, le=100.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Envelope(StrictModel):
    agent: str
    agent_version: str
    status: AgentStatus
    confidence: Confidence
    model: str | None = None
    started_at: datetime
    finished_at: datetime
    error: str | None = None
    raw_response_ref: str | None = None


class Classification(Envelope):
    doc_type: DocType
    routing_tags: list[str] = Field(default_factory=list)


class OcrField(StrictModel):
    key: str
    value: str
    confidence: Confidence
    page: int = Field(ge=1)


class BBox(StrictModel):
    text: str
    page: int = Field(ge=1)
    x: float
    y: float
    w: float
    h: float


class OcrPayload(Envelope):
    fields: list[OcrField]
    raw_text: str
    bounding_boxes: list[BBox]
    pages: int = Field(ge=0)
    used_text_layer: bool


class KycFlag(StrictModel):
    code: Literal[
        "MEMBER_NOT_FOUND",
        "DOB_MISMATCH",
        "NAME_MISMATCH",
        "POLICY_MISMATCH",
        "ID_EXPIRED",
        "ID_EXPIRING_SOON",
        "TAMPER_SUSPECTED",
        "LOW_QUALITY",
        "ELA_ANOMALY",
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    evidence: str


class KycResult(Envelope):
    kyc_passed: bool
    flags: list[KycFlag]
    member_ref: str | None


class ClaimFields(StrictModel):
    claim_amount: Decimal | None
    icd10_codes: list[str]
    cpt_codes: list[str]
    provider_npi: str | None
    service_date: date | None
    claim_number: str | None = None
    admit_date: date | None = None
    discharge_date: date | None = None
    signature_present: bool | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    field_confidence: dict[str, Confidence] = Field(default_factory=dict)
    field_source: dict[str, BBox | None] = Field(default_factory=dict)


class ClaimsResult(Envelope):
    extracted_fields: ClaimFields
    schema_valid: bool
    validation_errors: list[str]
    warnings: list[str] = Field(default_factory=list)


class PolicyClause(StrictModel):
    text: str
    policy_id: UUID
    page: int = Field(ge=1)
    section: str | None
    score: Score


class PolicyResult(Envelope):
    covered: bool | None
    coverage_percentage: CoveragePercentage | None
    policy_clause: PolicyClause | None
    exclusions: list[PolicyClause] = Field(default_factory=list)


class Anomaly(StrictModel):
    type: Literal[
        "DUPLICATE_CLAIM",
        "FREQUENCY_SPIKE",
        "PROVIDER_BILLING_OUTLIER",
        "AMOUNT_OUTLIER",
        "CODE_MISMATCH",
        "TAMPER_SIGNAL",
        "IDENTITY_MISMATCH",
        "NEAR_THRESHOLD",
        "DATE_CONFLICT",
        "READMISSION_30D",
    ]
    evidence: str
    weight: Score


class FraudResult(Envelope):
    fraud_score: Score
    anomalies: list[Anomaly]
    risk_level: RiskLevel


class RuleStep(StrictModel):
    rule: str
    fired: bool
    inputs: dict[str, JsonValue] = Field(default_factory=dict)


class Decision(Envelope):
    decision: DecisionKind
    justification: str
    agent_summaries: dict[str, str]
    rule_trace: list[RuleStep]


class DocumentRef(StrictModel):
    object_key: str
    mime_type: str
    pages: int | None = Field(default=None, ge=0)


class AuditEvent(StrictModel):
    case_id: str
    ts: datetime
    actor_type: Literal["SYSTEM", "AGENT", "USER"]
    actor: str
    event_type: Literal["NODE_START", "NODE_END", "DECISION", "OVERRIDE", "STATUS", "ERROR"]
    payload: dict[str, JsonValue]
