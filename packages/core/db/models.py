"""SQLAlchemy models for the MediShield relational schema."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TypeDecorator,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from packages.core.enums import CaseStatus, ClaimHistoryKind, DecisionKind, DocType, UserRole


def enum_values(enum_type: type[Enum]) -> list[str]:
    return [member.value for member in enum_type]


class ClaimHistoryKindType(TypeDecorator[ClaimHistoryKind]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: ClaimHistoryKind | str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return ClaimHistoryKind(value).value

    def process_result_value(self, value: str | None, dialect: Any) -> ClaimHistoryKind | None:
        if value is None:
            return None
        return ClaimHistoryKind(value)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_status_created_at", "status", "created_at"),
        Index("ix_cases_sha256", "sha256"),
    )

    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status", values_callable=enum_values), nullable=False
    )
    channel: Mapped[str | None] = mapped_column(Text)
    doc_type: Mapped[DocType | None] = mapped_column(
        Enum(DocType, name="doc_type", values_callable=enum_values)
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    duplicate_of: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("cases.case_id")
    )
    member_ref: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False
    )
    pipeline_run: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    agent_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Decision(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False
    )
    pipeline_run: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    decision: Mapped[DecisionKind] = mapped_column(
        Enum(DecisionKind, name="decision_kind", values_callable=enum_values), nullable=False
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    rule_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Override(Base):
    __tablename__ = "overrides"
    __table_args__ = (CheckConstraint("length(reason) >= 10", name="ck_overrides_reason_length"),)

    override_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    from_decision: Mapped[DecisionKind | None] = mapped_column(
        Enum(DecisionKind, name="decision_kind", values_callable=enum_values)
    )
    to_decision: Mapped[DecisionKind] = mapped_column(
        Enum(DecisionKind, name="decision_kind", values_callable=enum_values), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[str] = mapped_column(Text, primary_key=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    policy_number: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    policy_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    status: Mapped[str | None] = mapped_column(Text)
    id_doc_expiry: Mapped[date | None] = mapped_column(Date)


class ClaimHistory(Base):
    __tablename__ = "claim_history"
    __table_args__ = (
        Index("ix_claim_history_member_service_date", "member_id", "service_date"),
        Index("ix_claim_history_provider_npi", "provider_npi"),
        CheckConstraint(
            "kind IN ('PRIOR_CLAIM','EPISODE_CLAIM','PRIOR_STAY')",
            name="ck_claim_history_kind",
        ),
    )

    claim_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    member_id: Mapped[str | None] = mapped_column(Text, ForeignKey("members.member_id"))
    kind: Mapped[ClaimHistoryKind] = mapped_column(ClaimHistoryKindType(), nullable=False)
    claim_number: Mapped[str | None] = mapped_column(Text)
    provider_npi: Mapped[str | None] = mapped_column(String(10))
    cpt_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    icd10_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    service_date: Mapped[date | None] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admit_date: Mapped[date | None] = mapped_column(Date)
    discharge_date: Mapped[date | None] = mapped_column(Date)
    source_case_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    object_key: Mapped[str | None] = mapped_column(Text)
    ingest_status: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PolicyExclusion(Base):
    __tablename__ = "policy_exclusions"

    exclusion_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    policy_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("policies.policy_id"), nullable=False
    )
    range_start: Mapped[str] = mapped_column(Text, nullable=False)
    range_end: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=enum_values), nullable=False
    )
