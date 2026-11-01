from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr, ValidationError

from packages.core.config import Settings
from packages.core.enums import AgentStatus, DecisionKind, DocType, RiskLevel
from packages.core.models import (
    ClaimsResult,
    Classification,
    FraudResult,
    KycFlag,
    KycResult,
    OcrPayload,
    PolicyResult,
)
from packages.decision.engine import decide
from packages.decision.thresholds import Thresholds
from packages.graph.state import GraphState

NOW = datetime(2026, 1, 1, tzinfo=UTC)
DEFAULT_THRESHOLDS = Thresholds(
    fraud_escalate=0.30,
    fraud_high=0.60,
    agent_confidence=0.60,
    classify_review=0.60,
)


def envelope_data(
    agent: str,
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> dict[str, object]:
    return {
        "agent": agent,
        "agent_version": "test-1",
        "status": status,
        "confidence": confidence,
        "started_at": NOW,
        "finished_at": NOW,
    }


def classification(
    doc_type: DocType = DocType.CLAIM_FORM,
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> Classification:
    return Classification(
        **envelope_data("classifier", confidence, status),
        doc_type=doc_type,
    )


def ocr(
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> OcrPayload:
    return OcrPayload(
        **envelope_data("ocr", confidence, status),
        fields=[],
        raw_text="",
        bounding_boxes=[],
        pages=1,
        used_text_layer=True,
    )


def kyc(
    passed: bool = True,
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> KycResult:
    return KycResult(
        **envelope_data("kyc", confidence, status),
        kyc_passed=passed,
        flags=[],
        member_ref="member-1",
    )


def claims(
    schema_valid: bool = True,
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> ClaimsResult:
    return ClaimsResult(
        **envelope_data("claims", confidence, status),
        extracted_fields={
            "claim_amount": None,
            "icd10_codes": [],
            "cpt_codes": [],
            "provider_npi": None,
            "service_date": None,
        },
        schema_valid=schema_valid,
        validation_errors=[] if schema_valid else ["invalid claim schema"],
    )


def policy(
    covered: bool | None = True,
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> PolicyResult:
    return PolicyResult(
        **envelope_data("policy", confidence, status),
        covered=covered,
        coverage_percentage=80 if covered else None,
        policy_clause=None,
    )


def fraud(
    score: float = 0.0,
    confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> FraudResult:
    risk_level = (
        RiskLevel.HIGH if score >= 0.60 else RiskLevel.MEDIUM if score >= 0.30 else RiskLevel.LOW
    )
    return FraudResult(
        **envelope_data("fraud", confidence, status),
        fraud_score=score,
        anomalies=[],
        risk_level=risk_level,
    )


def claim_state(
    *,
    kyc_passed: bool = True,
    covered: bool | None = True,
    schema_valid: bool = True,
    fraud_score: float = 0.0,
    agent_confidence: float = 0.9,
    status: AgentStatus = AgentStatus.OK,
) -> GraphState:
    return {
        "classification": classification(confidence=agent_confidence),
        "ocr": ocr(confidence=agent_confidence),
        "kyc": kyc(kyc_passed, agent_confidence, status),
        "claims": claims(schema_valid, agent_confidence, status),
        "policy": policy(covered, agent_confidence, status),
        "fraud": fraud(fraud_score, agent_confidence, status),
    }


def id_state(
    *,
    kyc_passed: bool = True,
    fraud_score: float = 0.0,
) -> GraphState:
    return {
        "classification": classification(DocType.ID_DOCUMENT),
        "ocr": ocr(),
        "kyc": kyc(kyc_passed),
        "fraud": fraud(fraud_score),
    }


def amendment_state(*, kyc_passed: bool = True) -> GraphState:
    return {
        "classification": classification(DocType.POLICY_AMENDMENT),
        "ocr": ocr(),
        "kyc": kyc(kyc_passed),
        "policy": policy(True),
    }


def supporting_state(
    doc_type: DocType,
    *,
    covered: bool | None,
    schema_valid: bool = True,
    kyc_passed: bool = True,
    claims_warnings: list[str] | None = None,
    kyc_flags: list[KycFlag] | None = None,
) -> GraphState:
    claims_result = claims(schema_valid)
    claims_result.warnings = claims_warnings or []
    kyc_result = kyc(kyc_passed)
    kyc_result.flags = kyc_flags or []
    return {
        "classification": classification(doc_type),
        "ocr": ocr(),
        "kyc": kyc_result,
        "claims": claims_result,
        "policy": policy(covered),
        "fraud": fraud(),
    }


def test_thresholds_are_frozen_and_built_from_settings() -> None:
    settings = Settings(
        database_url="postgresql://localhost/medishield",
        redis_url="redis://localhost:6380/0",
        s3_endpoint="http://localhost:9000",
        s3_access_key=SecretStr("access"),
        s3_secret_key=SecretStr("secret"),
        s3_bucket="documents",
        qdrant_url="http://localhost:6333",
        qdrant_api_key=SecretStr("qdrant"),
        llm_vision_model="vision-model",
        llm_text_model="text-model",
        llm_fallback_model="fallback-model",
        jwt_secret=SecretStr("jwt"),
        threshold_fraud_escalate=0.25,
        threshold_fraud_high=0.70,
        threshold_agent_confidence=0.65,
        threshold_classify_review=0.55,
    )

    thresholds = Thresholds.from_settings(settings)

    assert thresholds.fraud_escalate == 0.25
    assert thresholds.fraud_high == 0.70
    assert thresholds.agent_confidence == 0.65
    assert thresholds.classify_review == 0.55
    with pytest.raises(ValidationError):
        thresholds.agent_confidence = 0.5


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (claim_state(), DecisionKind.APPROVE),
        (claim_state(kyc_passed=False), DecisionKind.REJECT),
        (claim_state(covered=False), DecisionKind.REJECT),
        (claim_state(schema_valid=False), DecisionKind.REJECT),
        (claim_state(fraud_score=0.30), DecisionKind.ESCALATE),
        (claim_state(agent_confidence=0.59), DecisionKind.ESCALATE),
        (claim_state(status=AgentStatus.ERROR), DecisionKind.ESCALATE),
    ],
)
def test_each_decision_rule_fires_alone(state: GraphState, expected: DecisionKind) -> None:
    decision, _, _ = decide(state, DEFAULT_THRESHOLDS)

    assert decision == expected


def test_rule_precedence_fraud_escalation_beats_kyc_rejection() -> None:
    decision, trace, _ = decide(claim_state(kyc_passed=False, fraud_score=0.5), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert [step.rule for step in trace] == ["R1_AGENT_RELIABILITY", "R2_FRAUD_SCORE"]
    assert trace[-1].fired is True


def test_agent_error_precedes_fraud_and_rejection() -> None:
    decision, trace, confidence = decide(
        claim_state(
            kyc_passed=False,
            fraud_score=0.9,
            status=AgentStatus.ERROR,
        ),
        DEFAULT_THRESHOLDS,
    )

    assert decision == DecisionKind.ESCALATE
    assert trace[0].rule == "R1_AGENT_RELIABILITY"
    assert trace[0].fired is True
    assert confidence == pytest.approx(0.59)


@pytest.mark.parametrize(
    ("fraud_score", "expected"),
    [(0.299999, DecisionKind.APPROVE), (0.30, DecisionKind.ESCALATE)],
)
def test_fraud_threshold_boundary(fraud_score: float, expected: DecisionKind) -> None:
    decision, _, _ = decide(claim_state(fraud_score=fraud_score), DEFAULT_THRESHOLDS)

    assert decision == expected


@pytest.mark.parametrize(
    ("agent_confidence", "expected"),
    [(0.60, DecisionKind.APPROVE), (0.599999, DecisionKind.ESCALATE)],
)
def test_agent_confidence_threshold_boundary(
    agent_confidence: float,
    expected: DecisionKind,
) -> None:
    decision, _, _ = decide(claim_state(agent_confidence=agent_confidence), DEFAULT_THRESHOLDS)

    assert decision == expected


def test_covered_none_triggers_low_confidence_escalation() -> None:
    decision, trace, _ = decide(claim_state(covered=None), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert trace[0].fired is True
    assert trace[0].inputs["coverage_undetermined"] is True


def test_skipped_agents_are_ignored_for_rules_and_confidence() -> None:
    state = claim_state()
    state["kyc"] = kyc(False, 0.0, AgentStatus.SKIPPED)
    state["claims"] = claims(False, 0.0, AgentStatus.SKIPPED)
    state["policy"] = policy(False, 0.0, AgentStatus.SKIPPED)
    state["fraud"] = fraud(0.9, 0.0, AgentStatus.SKIPPED)

    decision, _, confidence = decide(state, DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.APPROVE
    assert confidence == 0.9


def test_unrouted_outputs_may_be_absent_for_id_document() -> None:
    decision, _, confidence = decide(id_state(), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.APPROVE
    assert confidence == 0.9


def test_missing_routed_agent_output_escalates() -> None:
    state = claim_state()
    del state["claims"]

    decision, trace, confidence = decide(state, DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert trace[0].fired is True
    assert "claims" in trace[0].inputs["missing_agents"]
    assert confidence <= 0.59


def test_missing_classification_escalates_with_zero_confidence() -> None:
    decision, trace, confidence = decide({}, DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert trace[0].inputs["missing_agents"] == ["classification"]
    assert confidence == 0.0


def test_reject_from_one_source_gets_confidence_discount() -> None:
    decision, _, confidence = decide(claim_state(kyc_passed=False), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.REJECT
    assert confidence == pytest.approx(0.81)


def test_multiple_reject_sources_do_not_get_single_source_discount() -> None:
    decision, _, confidence = decide(
        claim_state(kyc_passed=False, covered=False), DEFAULT_THRESHOLDS
    )

    assert decision == DecisionKind.REJECT
    assert confidence == pytest.approx(0.9)


def test_escalation_from_reliability_is_capped_below_threshold() -> None:
    decision, _, confidence = decide(claim_state(agent_confidence=0.2), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert confidence == pytest.approx(0.2)


def test_escalation_cap_applies_to_high_confidence_agent_error() -> None:
    state = claim_state()
    state["ocr"] = ocr(0.9, AgentStatus.ERROR)

    decision, _, confidence = decide(state, DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert confidence == pytest.approx(0.59)


def test_fraud_escalation_is_not_subject_to_reliability_cap() -> None:
    decision, _, confidence = decide(claim_state(fraud_score=0.30), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert confidence == pytest.approx(0.9)


def test_id_document_uses_identity_checks_without_claim_conditions() -> None:
    decision, _, _ = decide(id_state(), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.APPROVE


def test_id_document_rejects_failed_kyc_and_escalates_high_fraud() -> None:
    rejected, _, _ = decide(id_state(kyc_passed=False), DEFAULT_THRESHOLDS)
    escalated, _, _ = decide(id_state(fraud_score=0.30), DEFAULT_THRESHOLDS)

    assert rejected == DecisionKind.REJECT
    assert escalated == DecisionKind.ESCALATE


def test_policy_amendment_escalates_for_human_confirmation() -> None:
    decision, trace, _ = decide(amendment_state(), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.ESCALATE
    assert trace[-1].rule == "POLICY_AMENDMENT_REVIEW"
    assert trace[-1].fired is True


def test_policy_amendment_rejects_failed_kyc() -> None:
    decision, _, _ = decide(amendment_state(kyc_passed=False), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.REJECT


@pytest.mark.parametrize("doc_type", [DocType.DISCHARGE_SUMMARY, DocType.PRESCRIPTION])
@pytest.mark.parametrize("covered", [False, None])
def test_supporting_documents_ignore_policy_result(
    doc_type: DocType,
    covered: bool | None,
) -> None:
    decision, trace, _ = decide(
        supporting_state(doc_type, covered=covered),
        DEFAULT_THRESHOLDS,
    )

    assert decision == DecisionKind.APPROVE
    assert "policy" not in trace[0].inputs["missing_agents"]


def test_invalid_prescription_schema_rejects_at_normal_confidence() -> None:
    decision, trace, confidence = decide(
        supporting_state(
            DocType.PRESCRIPTION,
            covered=False,
            schema_valid=False,
        ),
        DEFAULT_THRESHOLDS,
    )

    assert decision == DecisionKind.REJECT
    assert confidence == pytest.approx(0.81)
    assert trace[-1].inputs["rejection_reasons"] == ["SCHEMA_INVALID"]


@pytest.mark.parametrize("doc_type", list(DocType))
def test_claim_warnings_and_low_expiring_id_flag_do_not_change_decision(
    doc_type: DocType,
) -> None:
    state = supporting_state(
        doc_type,
        covered=True,
        claims_warnings=["NPI_CHECKSUM"],
        kyc_flags=[KycFlag(code="ID_EXPIRING_SOON", severity="LOW", evidence="near expiry")],
    )
    expected = (
        DecisionKind.ESCALATE
        if doc_type == DocType.POLICY_AMENDMENT
        else (
            DecisionKind.APPROVE
            if doc_type in (DocType.DISCHARGE_SUMMARY, DocType.PRESCRIPTION)
            else decide(claim_state(), DEFAULT_THRESHOLDS)[0]
        )
    )

    decision, _, _ = decide(state, DEFAULT_THRESHOLDS)

    assert decision == expected


def test_rule_trace_records_evaluated_rules_and_trigger_inputs() -> None:
    decision, trace, _ = decide(claim_state(covered=False), DEFAULT_THRESHOLDS)

    assert decision == DecisionKind.REJECT
    assert [step.rule for step in trace] == [
        "R1_AGENT_RELIABILITY",
        "R2_FRAUD_SCORE",
        "R3_REJECTION",
    ]
    assert [step.fired for step in trace] == [False, False, True]
    assert trace[-1].inputs["rejection_reasons"] == ["NOT_COVERED"]


@given(
    classifier_confidence=st.floats(min_value=0, max_value=1, allow_nan=False),
    other_confidence=st.floats(min_value=0, max_value=1, allow_nan=False),
    fraud_score=st.floats(min_value=0, max_value=1, allow_nan=False),
    kyc_passed=st.booleans(),
    covered=st.one_of(st.none(), st.booleans()),
    schema_valid=st.booleans(),
)
def test_decision_property_is_valid_and_never_approves_triggered_rules(
    classifier_confidence: float,
    other_confidence: float,
    fraud_score: float,
    kyc_passed: bool,
    covered: bool | None,
    schema_valid: bool,
) -> None:
    state = claim_state(
        kyc_passed=kyc_passed,
        covered=covered,
        schema_valid=schema_valid,
        fraud_score=fraud_score,
    )
    state["classification"] = classification(confidence=classifier_confidence)
    state["ocr"] = ocr(confidence=other_confidence)

    decision, _, _ = decide(state, DEFAULT_THRESHOLDS)
    rule_triggered = (
        classifier_confidence < DEFAULT_THRESHOLDS.agent_confidence
        or other_confidence < DEFAULT_THRESHOLDS.agent_confidence
        or covered is None
        or fraud_score >= DEFAULT_THRESHOLDS.fraud_escalate
        or not kyc_passed
        or covered is False
        or not schema_valid
    )

    assert decision in set(DecisionKind)
    if rule_triggered:
        assert decision != DecisionKind.APPROVE
