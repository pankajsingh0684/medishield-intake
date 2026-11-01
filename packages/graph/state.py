"""Typed LangGraph state shared by pipeline nodes."""

import operator
from typing import Annotated, TypedDict

from packages.core.models import (
    AuditEvent,
    ClaimsResult,
    Classification,
    Decision,
    DocumentRef,
    FraudResult,
    KycResult,
    OcrPayload,
    PolicyResult,
)


class GraphState(TypedDict, total=False):
    case_id: str
    pipeline_run: str
    document: DocumentRef
    classification: Classification
    ocr: OcrPayload
    kyc: KycResult
    claims: ClaimsResult
    policy: PolicyResult
    fraud: FraudResult
    decision: Decision
    errors: Annotated[list[str], operator.add]
    audit: Annotated[list[AuditEvent], operator.add]
