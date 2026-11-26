"""Pure deterministic decision function over completed graph outputs."""

from packages.core.enums import AgentStatus, DecisionKind, DocType
from packages.core.models import (
    ClaimsResult,
    Classification,
    Envelope,
    FraudResult,
    KycResult,
    OcrPayload,
    PolicyResult,
    RuleStep,
)
from packages.decision.thresholds import Thresholds
from packages.graph.state import GraphState

type AgentResult = (
    Envelope | Classification | OcrPayload | KycResult | ClaimsResult | PolicyResult | FraudResult
)

_ROUTED_AGENTS: dict[DocType, tuple[str, ...]] = {
    DocType.CLAIM_FORM: ("classification", "ocr", "kyc", "claims", "policy", "fraud"),
    DocType.ID_DOCUMENT: ("classification", "ocr", "kyc", "fraud"),
    DocType.DISCHARGE_SUMMARY: (
        "classification",
        "ocr",
        "kyc",
        "claims",
        "fraud",
    ),
    DocType.PRESCRIPTION: (
        "classification",
        "ocr",
        "kyc",
        "claims",
        "fraud",
    ),
    DocType.POLICY_AMENDMENT: ("classification", "ocr", "kyc", "policy"),
    DocType.UNKNOWN: ("classification", "ocr"),
}


def _routed_agent_names(state: GraphState) -> tuple[str, ...]:
    classification = state.get("classification")
    if classification is None:
        return ("classification",)
    return _ROUTED_AGENTS[classification.doc_type]


def _collect_agent_results(
    state: GraphState,
    routed_agent_names: tuple[str, ...],
) -> tuple[dict[str, AgentResult], list[str]]:
    state_results: dict[str, AgentResult | None] = {
        "classification": state.get("classification"),
        "ocr": state.get("ocr"),
        "kyc": state.get("kyc"),
        "claims": state.get("claims"),
        "policy": state.get("policy"),
        "fraud": state.get("fraud"),
    }
    applicable: dict[str, AgentResult] = {}
    missing: list[str] = []

    for agent_name in routed_agent_names:
        result = state_results[agent_name]
        if result is None:
            missing.append(agent_name)
        elif result.status != AgentStatus.SKIPPED:
            applicable[agent_name] = result

    return applicable, missing


def _confidence(results: dict[str, AgentResult]) -> float:
    confidences = [result.confidence for result in results.values()]
    if not confidences:
        return 0.0
    return min(confidences)


def decide(
    state: GraphState,
    cfg: Thresholds,
) -> tuple[DecisionKind, list[RuleStep], float]:
    """Apply precedence rules and return decision, trace, and confidence."""
    classification = state.get("classification")
    if classification is not None and classification.doc_type == DocType.UNKNOWN:
        return (
            DecisionKind.ESCALATE,
            [
                RuleStep(
                    rule="UNKNOWN_DOCUMENT_TYPE",
                    fired=True,
                    inputs={"reason": "UNKNOWN_DOCUMENT_TYPE"},
                )
            ],
            min(classification.confidence, 0.59),
        )
    routed_agent_names = _routed_agent_names(state)
    results, missing_agents = _collect_agent_results(state, routed_agent_names)
    confidence = _confidence(results)

    error_agents = [name for name, result in results.items() if result.status == AgentStatus.ERROR]
    low_confidence_agents = [
        name for name, result in results.items() if result.confidence < cfg.agent_confidence
    ]
    policy_result = results.get("policy")
    coverage_undetermined = (
        isinstance(policy_result, PolicyResult) and policy_result.covered is None
    )
    if coverage_undetermined:
        low_confidence_agents.append("policy_coverage")

    r1_fired = bool(error_agents or low_confidence_agents or missing_agents)
    trace = [
        RuleStep(
            rule="R1_AGENT_RELIABILITY",
            fired=r1_fired,
            inputs={
                "applicable_agents": {
                    name: {
                        "status": result.status.value,
                        "confidence": result.confidence,
                    }
                    for name, result in results.items()
                },
                "error_agents": error_agents,
                "low_confidence_agents": low_confidence_agents,
                "missing_agents": missing_agents,
                "coverage_undetermined": coverage_undetermined,
                "threshold": cfg.agent_confidence,
            },
        )
    ]
    fraud_result = results.get("fraud")
    fraud_score = fraud_result.fraud_score if isinstance(fraud_result, FraudResult) else None
    r2_fired = fraud_score is not None and fraud_score >= cfg.fraud_escalate
    trace.append(
        RuleStep(
            rule="R2_FRAUD_SCORE",
            fired=r2_fired,
            inputs={"fraud_score": fraud_score, "threshold": cfg.fraud_escalate},
        )
    )
    classification = state.get("classification")
    is_policy_amendment = (
        classification is not None and classification.doc_type == DocType.POLICY_AMENDMENT
    )
    is_supporting_document = classification is not None and classification.doc_type in (
        DocType.DISCHARGE_SUMMARY,
        DocType.PRESCRIPTION,
    )
    rejection_reasons: list[str] = []
    rejection_sources: list[str] = []
    kyc_result = results.get("kyc")
    claims_result = results.get("claims")

    if isinstance(kyc_result, KycResult) and not kyc_result.kyc_passed:
        rejection_reasons.append("KYC_FAILED")
        rejection_sources.append("kyc")
    if not is_policy_amendment:
        if (
            not is_supporting_document
            and isinstance(policy_result, PolicyResult)
            and policy_result.covered is False
        ):
            rejection_reasons.append("NOT_COVERED")
            rejection_sources.append("policy")
        if isinstance(claims_result, ClaimsResult) and not claims_result.schema_valid:
            rejection_reasons.append("SCHEMA_INVALID")
            rejection_sources.append("claims")

    r3_fired = bool(rejection_reasons)
    trace.append(
        RuleStep(
            rule="R3_REJECTION",
            fired=r3_fired,
            inputs={
                "rejection_reasons": rejection_reasons,
                "rejection_sources": rejection_sources,
            },
        )
    )
    if is_policy_amendment:
        amendment_fired = not (r1_fired or r2_fired or r3_fired)
        trace.append(
            RuleStep(
                rule="POLICY_AMENDMENT_REVIEW",
                fired=amendment_fired,
                inputs={
                    "reason": "human confirmation required",
                    "blocked_by": [step.rule for step in trace if step.fired],
                },
            )
        )
    trace.append(
        RuleStep(
            rule="R4_APPROVE",
            fired=not (r1_fired or r2_fired or r3_fired or is_policy_amendment),
            inputs={
                "applicable_agent_count": len(results),
                "blocked_by": [step.rule for step in trace if step.fired],
            },
        )
    )

    if r1_fired:
        return DecisionKind.ESCALATE, trace, min(confidence, 0.59)
    if r2_fired:
        return DecisionKind.ESCALATE, trace, confidence
    if r3_fired:
        if len(rejection_sources) == 1:
            confidence *= 0.9
        return DecisionKind.REJECT, trace, confidence
    if is_policy_amendment:
        return DecisionKind.ESCALATE, trace, confidence
    return DecisionKind.APPROVE, trace, confidence
