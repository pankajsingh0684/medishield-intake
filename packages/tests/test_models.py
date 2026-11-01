from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from packages.core.enums import (
    AgentStatus,
    CaseStatus,
    ClaimHistoryKind,
    DecisionKind,
    DocType,
    RiskLevel,
    UserRole,
)
from packages.core.models import (
    Anomaly,
    AuditEvent,
    BBox,
    ClaimFields,
    ClaimsResult,
    Classification,
    Decision,
    DocumentRef,
    Envelope,
    FraudResult,
    KycFlag,
    KycResult,
    OcrField,
    OcrPayload,
    PolicyClause,
    PolicyResult,
    RuleStep,
)
from packages.graph.state import GraphState

STARTED_AT = datetime(2026, 1, 1, tzinfo=UTC)
FINISHED_AT = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
POLICY_ID = UUID("00000000-0000-0000-0000-000000000001")


def envelope_values() -> dict[str, object]:
    return {
        "agent": "test-agent",
        "agent_version": "1.0",
        "status": AgentStatus.OK,
        "confidence": 0.9,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
    }


def valid_models() -> list[BaseModel]:
    bbox = BBox(text="member id", page=1, x=0, y=0, w=0.5, h=0.1)
    clause = PolicyClause(
        text="Covered service",
        policy_id=POLICY_ID,
        page=1,
        section="Coverage",
        score=0.95,
    )
    claim_fields = ClaimFields(
        claim_amount=Decimal("125.50"),
        icd10_codes=["A00.0"],
        cpt_codes=["12345"],
        provider_npi="1234567890",
        service_date=date(2026, 1, 1),
        field_confidence={"claim_amount": 0.9},
        field_source={"claim_amount": bbox},
    )
    rule_step = RuleStep(rule="R4", fired=True, inputs={"fraud_score": 0.1})

    return [
        Envelope(**envelope_values()),
        Classification(**envelope_values(), doc_type=DocType.CLAIM_FORM),
        OcrField(key="member_id", value="member-1", confidence=0.9, page=1),
        bbox,
        OcrPayload(
            **envelope_values(),
            fields=[OcrField(key="member_id", value="member-1", confidence=0.9, page=1)],
            raw_text="member-1",
            bounding_boxes=[bbox],
            pages=1,
            used_text_layer=True,
        ),
        KycFlag(code="ID_EXPIRED", severity="HIGH", evidence="page 1"),
        KycResult(
            **envelope_values(),
            kyc_passed=False,
            flags=[KycFlag(code="ID_EXPIRED", severity="HIGH", evidence="page 1")],
            member_ref=None,
        ),
        claim_fields,
        ClaimsResult(
            **envelope_values(),
            extracted_fields=claim_fields,
            schema_valid=True,
            validation_errors=[],
            warnings=["NPI_CHECKSUM"],
        ),
        clause,
        PolicyResult(
            **envelope_values(),
            covered=True,
            coverage_percentage=80,
            policy_clause=clause,
        ),
        Anomaly(type="DUPLICATE_CLAIM", evidence="claim-1", weight=0.5),
        FraudResult(
            **envelope_values(),
            fraud_score=0.2,
            anomalies=[Anomaly(type="DUPLICATE_CLAIM", evidence="claim-1", weight=0.5)],
            risk_level=RiskLevel.LOW,
        ),
        rule_step,
        Decision(
            **envelope_values(),
            decision=DecisionKind.APPROVE,
            justification="All checks passed.",
            agent_summaries={"claims": "Valid"},
            rule_trace=[rule_step],
        ),
        DocumentRef(
            object_key="raw/2026/01/case/original.pdf", mime_type="application/pdf", pages=1
        ),
        AuditEvent(
            case_id="case-1",
            ts=STARTED_AT,
            actor_type="AGENT",
            actor="classifier",
            event_type="NODE_START",
            payload={"pipeline_run": "run-1"},
        ),
    ]


@pytest.mark.parametrize("model", valid_models(), ids=lambda model: type(model).__name__)
def test_models_round_trip_json_and_produce_schema(model: BaseModel) -> None:
    model_type = type(model)

    restored = model_type.model_validate_json(model.model_dump_json())

    assert restored == model
    assert model_type.model_json_schema()["title"] == model_type.__name__


@pytest.mark.parametrize("model", valid_models(), ids=lambda model: type(model).__name__)
def test_models_forbid_extra_fields(model: BaseModel) -> None:
    payload = model.model_dump(mode="json")
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        type(model).model_validate(payload)


@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (Envelope, {**envelope_values(), "confidence": -0.01}),
        (
            OcrField,
            {"key": "field", "value": "value", "confidence": 1.01, "page": 1},
        ),
        (
            ClaimFields,
            {
                "claim_amount": None,
                "icd10_codes": [],
                "cpt_codes": [],
                "provider_npi": None,
                "service_date": None,
                "field_confidence": {"amount": 1.01},
            },
        ),
        (
            PolicyClause,
            {
                "text": "Clause",
                "policy_id": str(POLICY_ID),
                "page": 1,
                "section": None,
                "score": 1.01,
            },
        ),
        (Anomaly, {"type": "TAMPER_SIGNAL", "evidence": "page 1", "weight": -0.1}),
        (
            FraudResult,
            {
                **envelope_values(),
                "fraud_score": 1.01,
                "anomalies": [],
                "risk_level": RiskLevel.HIGH,
            },
        ),
        (
            PolicyResult,
            {
                **envelope_values(),
                "covered": True,
                "coverage_percentage": 100.01,
                "policy_clause": None,
            },
        ),
    ],
)
def test_numeric_bounds_are_enforced(
    model_type: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


def test_graph_state_schema_is_available() -> None:
    schema = TypeAdapter(cast(type, GraphState)).json_schema()

    assert "case_id" in schema["properties"]
    assert "audit" in schema["properties"]


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (
            DocType,
            (
                "CLAIM_FORM",
                "ID_DOCUMENT",
                "DISCHARGE_SUMMARY",
                "PRESCRIPTION",
                "POLICY_AMENDMENT",
                "UNKNOWN",
            ),
        ),
        (DecisionKind, ("APPROVE", "REJECT", "ESCALATE")),
        (RiskLevel, ("LOW", "MEDIUM", "HIGH")),
        (
            CaseStatus,
            (
                "RECEIVED",
                "CLASSIFIED",
                "PROCESSING",
                "FRAUD_CHECK",
                "AGGREGATED",
                "DECIDED",
                "NEEDS_REVIEW",
                "OVERRIDDEN",
                "FAILED",
            ),
        ),
        (UserRole, ("REVIEWER", "SUPERVISOR", "AUDITOR", "ADMIN")),
        (AgentStatus, ("OK", "ERROR", "SKIPPED")),
        (ClaimHistoryKind, ("PRIOR_CLAIM", "EPISODE_CLAIM", "PRIOR_STAY")),
    ],
)
def test_enum_values_match_spec(enum_type: type, expected: tuple[str, ...]) -> None:
    assert tuple(member.value for member in enum_type) == expected
