"""Typed persistence interfaces for core database records."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from packages.core.db.models import (
    AgentRun,
    AuditEvent,
    Case,
    ClaimHistory,
    Member,
    Policy,
    PolicyExclusion,
)
from packages.core.enums import CaseStatus, ClaimHistoryKind


def _shape_class(code: str) -> str:
    """Leading letter (V2100), digits ending in a letter (0001T), or digits only (17000)."""
    if code[:1].isalpha():
        return "leading_letter"
    return "trailing_letter" if code[-1:].isalpha() else "digits"


def code_in_range(code: str, range_start: str, range_end: str) -> bool:
    """Codes only match ranges of their own shape class, compared as upper-case strings."""
    code, start, end = code.strip().upper(), range_start.strip().upper(), range_end.strip().upper()
    if not code or not start or not end:
        return False
    if not _shape_class(code) == _shape_class(start) == _shape_class(end):
        return False
    return start <= code <= end


class CaseRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, case: Case) -> Case:
        self._session.add(case)
        self._session.flush()
        return case

    def get(self, case_id: UUID) -> Case | None:
        return self._session.get(Case, case_id)

    def update_status(self, case_id: UUID, status: CaseStatus) -> Case:
        case = self.get(case_id)
        if case is None:
            raise LookupError(f"Case not found: {case_id}")
        case.status = status
        self._session.flush()
        return case

    def update_classification(self, case_id: UUID, doc_type: Any) -> Case:
        case = self.get(case_id)
        if case is None:
            raise LookupError(f"Case not found: {case_id}")
        case.doc_type = doc_type
        self._session.flush()
        return case

    def list(
        self,
        *,
        status: CaseStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Case]:
        statement: Select[tuple[Case]] = select(Case).order_by(Case.created_at.desc())
        if status is not None:
            statement = statement.where(Case.status == status)
        return list(self._session.scalars(statement.limit(limit).offset(offset)))


class AgentRunRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, run: AgentRun) -> AgentRun:
        existing = self._session.scalar(
            select(AgentRun).where(
                AgentRun.case_id == run.case_id,
                AgentRun.pipeline_run == run.pipeline_run,
                AgentRun.agent == run.agent,
            )
        )
        if existing is None:
            self._session.add(run)
            self._session.flush()
            return run
        for attribute in (
            "agent_version",
            "status",
            "model",
            "prompt_version",
            "confidence",
            "output",
            "error",
            "tokens_in",
            "tokens_out",
            "started_at",
            "finished_at",
        ):
            setattr(existing, attribute, getattr(run, attribute))
        self._session.flush()
        return existing


class MemberRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, member: Member) -> Member:
        self._session.add(member)
        self._session.flush()
        return member

    def get(self, member_id: str) -> Member | None:
        return self._session.get(Member, member_id)

    def get_by_policy_number(self, policy_number: str) -> Member | None:
        statement = select(Member).where(Member.policy_number == policy_number).limit(1)
        return self._session.scalar(statement)

    def get_by_date_of_birth(self, date_of_birth: date) -> list[Member]:
        statement = (
            select(Member).where(Member.date_of_birth == date_of_birth).order_by(Member.member_id)
        )
        return list(self._session.scalars(statement))

    def get_policy(self, member: Member) -> Policy | None:
        if member.policy_id is None:
            return None
        return self._session.get(Policy, member.policy_id)

    def get_policy_for_number(self, policy_number: str, service_date: date) -> Policy | None:
        normalized = policy_number.strip().upper()
        plan_code = (
            "GOLD"
            if normalized.startswith(("MED-GLD-", "POL-TEST-"))
            else "SILVER"
            if normalized.startswith("MED-SLV-")
            else None
        )
        if plan_code is None:
            return None
        statement = (
            select(Policy)
            .where(
                Policy.plan_code == plan_code,
                (Policy.effective_from.is_(None)) | (Policy.effective_from <= service_date),
                (Policy.effective_to.is_(None)) | (Policy.effective_to >= service_date),
            )
            .order_by(Policy.effective_from.desc().nullslast(), Policy.created_at.desc())
            .limit(1)
        )
        return self._session.scalar(statement)


class ClaimHistoryRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, claim: ClaimHistory) -> ClaimHistory:
        self._session.add(claim)
        self._session.flush()
        return claim

    def for_member(
        self,
        member_id: str,
        *,
        kind: ClaimHistoryKind | None = None,
        service_date_from: date | None = None,
        service_date_to: date | None = None,
        limit: int = 500,
    ) -> list[ClaimHistory]:
        statement: Select[tuple[ClaimHistory]] = select(ClaimHistory).where(
            ClaimHistory.member_id == member_id
        )
        if kind is not None:
            statement = statement.where(ClaimHistory.kind == kind)
        if service_date_from is not None:
            statement = statement.where(ClaimHistory.service_date >= service_date_from)
        if service_date_to is not None:
            statement = statement.where(ClaimHistory.service_date <= service_date_to)
        statement = statement.order_by(ClaimHistory.service_date.desc()).limit(limit)
        return list(self._session.scalars(statement))

    def for_member_and_kind(
        self,
        member_id: str,
        kind: ClaimHistoryKind,
        *,
        limit: int = 500,
    ) -> list[ClaimHistory]:
        return self.for_member(member_id, kind=kind, limit=limit)

    def by_claim_number(self, claim_number: str) -> list[ClaimHistory]:
        statement = select(ClaimHistory).where(ClaimHistory.claim_number == claim_number)
        return list(self._session.scalars(statement))


class PolicyExclusionRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(self, policy_id: UUID, cpt_code: str) -> list[PolicyExclusion]:
        statement = select(PolicyExclusion).where(PolicyExclusion.policy_id == policy_id)
        return [
            row
            for row in self._session.scalars(statement)
            if code_in_range(cpt_code, row.range_start, row.range_end)
        ]


class AuditRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        case_id: UUID,
        actor_type: str,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> AuditEvent:
        event = AuditEvent(
            case_id=case_id,
            actor_type=actor_type,
            actor=actor,
            event_type=event_type,
            payload=payload,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def for_case(self, case_id: UUID) -> list[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.event_id.asc())
        )
        return list(self._session.scalars(statement))
