"""Shared domain enums used by agents, graph state, and decisions."""

from enum import StrEnum


class DocType(StrEnum):
    CLAIM_FORM = "CLAIM_FORM"
    ID_DOCUMENT = "ID_DOCUMENT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    PRESCRIPTION = "PRESCRIPTION"
    POLICY_AMENDMENT = "POLICY_AMENDMENT"
    UNKNOWN = "UNKNOWN"


class DecisionKind(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CaseStatus(StrEnum):
    RECEIVED = "RECEIVED"
    CLASSIFIED = "CLASSIFIED"
    PROCESSING = "PROCESSING"
    FRAUD_CHECK = "FRAUD_CHECK"
    AGGREGATED = "AGGREGATED"
    DECIDED = "DECIDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    OVERRIDDEN = "OVERRIDDEN"
    FAILED = "FAILED"


class UserRole(StrEnum):
    REVIEWER = "REVIEWER"
    SUPERVISOR = "SUPERVISOR"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"


class AgentStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class ClaimHistoryKind(StrEnum):
    PRIOR_CLAIM = "PRIOR_CLAIM"
    EPISODE_CLAIM = "EPISODE_CLAIM"
    PRIOR_STAY = "PRIOR_STAY"
