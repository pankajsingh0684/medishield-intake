"""Typed persistence interfaces for core database records."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from packages.core.db.models import AuditEvent, Case, ClaimHistory, Member, PolicyExclusion
from packages.core.enums import CaseStatus, ClaimHistoryKind


class CaseRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, case: Case) -> Case:
        self._session.add(case)
        self._session.flush()
        return case

    def get(self, case_id: UUID) -> Case | None:
        return self._session.get(Case, case_id)

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
        normalized_code = cpt_code.upper()
        code_length = len(normalized_code)
        statement = select(PolicyExclusion).where(
            PolicyExclusion.policy_id == policy_id,
            func.length(func.upper(PolicyExclusion.range_start)) == code_length,
            func.length(func.upper(PolicyExclusion.range_end)) == code_length,
            func.upper(PolicyExclusion.range_start) <= normalized_code,
            func.upper(PolicyExclusion.range_end) >= normalized_code,
        )
        return list(self._session.scalars(statement))


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
