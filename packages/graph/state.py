"""Typed LangGraph state shared by pipeline nodes."""

import operator
from datetime import datetime
from typing import Annotated, TypedDict

from packages.core.enums import DocType
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
    fixed_doc_type: DocType
    document: DocumentRef
    received_at: datetime
    content: bytes
    images: tuple[bytes, ...]
    infrastructure_error: str
    routed_agents: list[str]
    classification: Classification
    ocr: OcrPayload
    kyc: KycResult
    claims: ClaimsResult
    policy: PolicyResult
    fraud: FraudResult
    decision: Decision
    terminal_status: str
    errors: Annotated[list[str], operator.add]
    audit: Annotated[list[AuditEvent], operator.add]
