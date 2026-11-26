"""Graph node implementations and their shared runtime dependencies."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from packages.agents.claims.agent import CLAIMS_VERSION, ClaimsAgent
from packages.agents.classifier.agent import CLASSIFIER_VERSION, ClassifierAgent
from packages.agents.fraud.agent import FRAUD_VERSION, FraudAgent
from packages.agents.fraud.weights import DETECTOR_WEIGHTS
from packages.agents.kyc.agent import KYC_VERSION, KycAgent
from packages.agents.ocr.agent import OCR_VERSION, OCRAgent
from packages.agents.policy.agent import POLICY_VERSION, PolicyAgent
from packages.core.clients import create_qdrant_client
from packages.core.db.models import Decision as DecisionRow
from packages.core.db.repositories import (
    AuditRepo,
    CaseRepo,
    ClaimHistoryRepo,
    DecisionRepo,
    MemberRepo,
    PolicyExclusionRepo,
)
from packages.core.documents import render_document
from packages.core.enums import AgentStatus, CaseStatus, DecisionKind, DocType, RiskLevel
from packages.core.events import EventPublisher, NoOpEventPublisher
from packages.core.llm.prompts import PromptLoader
from packages.core.llm.protocol import LLMGateway
from packages.core.models import (
    ClaimFields,
    ClaimsResult,
    Classification,
    Decision,
    DocumentRef,
    FraudResult,
    JustificationDraft,
    KycResult,
    OcrPayload,
    PolicyResult,
    RuleStep,
)
from packages.core.storage import S3Storage
from packages.decision.engine import decide
from packages.decision.thresholds import Thresholds
from packages.graph.routing import ROUTING_TABLE, route
from packages.graph.state import GraphState
from packages.graph.wrapper import InfrastructureFailure, instrument
from packages.rag.embeddings import LocalSentenceTransformerEmbedder
from packages.rag.retrieve import (
    CrossEncoderReranker,
    DeterministicReranker,
    QdrantHybridRetriever,
)

logger = logging.getLogger(__name__)
ORCHESTRATOR_VERSION = "1.0.0"


@dataclass
class GraphRuntime:
    engine: Engine
    storage: S3Storage
    settings: Any
    gateway: LLMGateway
    redis_client: Redis | None = None
    agent_overrides: dict[str, Callable[[GraphState], Any]] = field(default_factory=dict)
    retry_backoff_seconds: float = 1.0
    event_publisher: EventPublisher = field(default_factory=NoOpEventPublisher)


def _envelope_values(
    agent: str,
    version: str,
    status: AgentStatus,
    started_at: datetime,
    finished_at: datetime,
    model: str | None,
    confidence: float,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "agent_version": version,
        "status": status,
        "confidence": confidence,
        "model": model,
        "started_at": started_at,
        "finished_at": finished_at,
        "error": error,
    }


def _error_classification(start: datetime, finish: datetime, error: Exception) -> Classification:
    return Classification(
        **_envelope_values(
            "classifier",
            CLASSIFIER_VERSION,
            AgentStatus.ERROR,
            start,
            finish,
            None,
            0.0,
            type(error).__name__,
        ),
        doc_type=DocType.UNKNOWN,
        routing_tags=["NEEDS_REVIEW"],
    )


def _error_ocr(start: datetime, finish: datetime, error: Exception) -> OcrPayload:
    return OcrPayload(
        **_envelope_values(
            "ocr", OCR_VERSION, AgentStatus.ERROR, start, finish, None, 0.0, type(error).__name__
        ),
        fields=[],
        raw_text="",
        bounding_boxes=[],
        pages=0,
        used_text_layer=False,
    )


def _error_kyc(start: datetime, finish: datetime, error: Exception) -> KycResult:
    return KycResult(
        **_envelope_values(
            "kyc", KYC_VERSION, AgentStatus.ERROR, start, finish, None, 0.0, type(error).__name__
        ),
        kyc_passed=False,
        flags=[],
        member_ref=None,
    )


def _error_claims(start: datetime, finish: datetime, error: Exception) -> ClaimsResult:
    return ClaimsResult(
        **_envelope_values(
            "claims",
            CLAIMS_VERSION,
            AgentStatus.ERROR,
            start,
            finish,
            None,
            0.0,
            type(error).__name__,
        ),
        extracted_fields=ClaimFields(
            claim_amount=None,
            icd10_codes=[],
            cpt_codes=[],
            provider_npi=None,
            service_date=None,
        ),
        schema_valid=False,
        validation_errors=[f"CLAIMS_ERROR: {type(error).__name__}"],
    )


def _skipped_kyc() -> KycResult:
    now = datetime.now(UTC)
    return KycResult(
        **_envelope_values("kyc", KYC_VERSION, AgentStatus.SKIPPED, now, now, None, 1.0),
        kyc_passed=True,
        flags=[],
        member_ref=None,
    )


def _skipped_claims() -> ClaimsResult:
    now = datetime.now(UTC)
    return ClaimsResult(
        **_envelope_values("claims", CLAIMS_VERSION, AgentStatus.SKIPPED, now, now, None, 1.0),
        extracted_fields=ClaimFields(
            claim_amount=None,
            icd10_codes=[],
            cpt_codes=[],
            provider_npi=None,
            service_date=None,
        ),
        schema_valid=True,
        validation_errors=[],
    )


def _placeholder_policy() -> PolicyResult:
    now = datetime.now(UTC)
    return PolicyResult(
        **_envelope_values("policy", POLICY_VERSION, AgentStatus.SKIPPED, now, now, None, 1.0),
        covered=None,
        coverage_percentage=None,
        policy_clause=None,
        exclusions=[],
    )


def _error_policy(start: datetime, finish: datetime, error: Exception) -> PolicyResult:
    return PolicyResult(
        **_envelope_values(
            "policy",
            POLICY_VERSION,
            AgentStatus.ERROR,
            start,
            finish,
            None,
            0.0,
            type(error).__name__,
        ),
        covered=None,
        coverage_percentage=None,
        policy_clause=None,
        exclusions=[],
    )


def _placeholder_fraud() -> FraudResult:
    now = datetime.now(UTC)
    return FraudResult(
        **_envelope_values("fraud", "0.1.0", AgentStatus.SKIPPED, now, now, None, 1.0),
        fraud_score=0.0,
        anomalies=[],
        risk_level=RiskLevel.LOW,
    )


def _error_fraud(start: datetime, finish: datetime, error: Exception) -> FraudResult:
    return FraudResult(
        **_envelope_values(
            "fraud",
            FRAUD_VERSION,
            AgentStatus.ERROR,
            start,
            finish,
            None,
            0.5,
            type(error).__name__,
        ),
        fraud_score=0.0,
        anomalies=[],
        risk_level=RiskLevel.LOW,
    )


def _template_justification(
    rule_trace: list[RuleStep],
    state: GraphState | None = None,
) -> str:
    fired_rules = [step.rule for step in rule_trace if step.fired]
    kyc_result = state.get("kyc") if state is not None else None
    if kyc_result is None or kyc_result.status != AgentStatus.OK:
        kyc_fact = "KYC unknown"
    else:
        kyc_fact = "KYC passed" if kyc_result.kyc_passed else "KYC failed"

    policy_result = state.get("policy") if state is not None else None
    if policy_result is None or policy_result.status != AgentStatus.OK:
        coverage_fact = "covered unknown"
    else:
        coverage = (
            "unknown"
            if policy_result.covered is None
            else "true"
            if policy_result.covered
            else "false"
        )
        coverage_fact = f"covered {coverage}"

    fraud_result = state.get("fraud") if state is not None else None
    if fraud_result is None or fraud_result.status != AgentStatus.OK:
        fraud_fact = "fraud score unknown, risk level unknown"
    else:
        fraud_fact = (
            f"fraud score {fraud_result.fraud_score:.2f}, "
            f"risk level {fraud_result.risk_level.value}"
        )

    rule_fact = ", ".join(fired_rules) if fired_rules else "no rules"
    return f"Rule trace fired: {rule_fact}. {kyc_fact}; {coverage_fact}; {fraud_fact}."


def _error_orchestrator(start: datetime, finish: datetime, error: Exception) -> Decision:
    trace = [
        RuleStep(
            rule="R1_AGENT_RELIABILITY",
            fired=True,
            inputs={"error_agents": ["orchestrator"], "error": type(error).__name__},
        ),
        RuleStep(rule="R2_FRAUD_SCORE", fired=False, inputs={"fraud_score": None}),
        RuleStep(rule="R3_REJECTION", fired=False, inputs={"rejection_reasons": []}),
        RuleStep(rule="R4_APPROVE", fired=False, inputs={"blocked_by": ["R1_AGENT_RELIABILITY"]}),
    ]
    return Decision(
        **_envelope_values(
            "orchestrator",
            ORCHESTRATOR_VERSION,
            AgentStatus.ERROR,
            start,
            finish,
            None,
            0.0,
            type(error).__name__,
        ),
        decision=DecisionKind.ESCALATE,
        justification=_template_justification(trace),
        agent_summaries={},
        rule_trace=trace,
    )


def _write_status(
    runtime: GraphRuntime,
    case_id: UUID,
    status: CaseStatus,
    actor: str,
    payload: dict[str, Any],
) -> None:
    try:
        with Session(runtime.engine) as session, session.begin():
            CaseRepo(session).update_status(case_id, status)
            AuditRepo(session).append(
                case_id=case_id,
                actor_type="AGENT",
                actor=actor,
                event_type="STATUS",
                payload=payload,
            )
    except Exception as error:
        raise InfrastructureFailure("Could not persist case status") from error


def _record_load_event(
    runtime: GraphRuntime,
    case_id: UUID,
    pipeline_run: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    with Session(runtime.engine) as session, session.begin():
        AuditRepo(session).append(
            case_id=case_id,
            actor_type="AGENT",
            actor="load_document",
            event_type=event_type,
            payload={"pipeline_run": str(pipeline_run), **payload},
        )


def _record_graph_event(
    runtime: GraphRuntime,
    state: GraphState,
    node: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        with Session(runtime.engine) as session, session.begin():
            AuditRepo(session).append(
                case_id=UUID(state["case_id"]),
                actor_type="AGENT",
                actor=node,
                event_type=event_type,
                payload={"pipeline_run": state["pipeline_run"], **(payload or {})},
            )
    except Exception as error:
        raise InfrastructureFailure(f"Could not persist {node} audit event") from error


def build_nodes(runtime: GraphRuntime) -> dict[str, Callable[[GraphState], dict[str, Any]]]:
    timeout = runtime.settings.agent_timeout_s

    def load_document(state: GraphState) -> dict[str, Any]:
        case_id = UUID(state["case_id"])
        pipeline_run = UUID(state["pipeline_run"])
        try:
            _record_load_event(runtime, case_id, pipeline_run, "NODE_START", {})
            with Session(runtime.engine) as session, session.begin():
                case = CaseRepo(session).get(case_id)
                if case is None:
                    raise LookupError("Case does not exist")
                content = runtime.storage.get(case.object_key)
                rendered = render_document(content, case.mime_type)
                doc_ref = DocumentRef(
                    object_key=case.object_key,
                    mime_type=case.mime_type,
                    pages=case.page_count or rendered.page_count,
                )
                received_at = case.received_at
                fixed_doc_type = state.get("fixed_doc_type")
                fixed_classification = None
                if fixed_doc_type is not None:
                    CaseRepo(session).update_classification(case_id, fixed_doc_type)
                    now = datetime.now(UTC)
                    fixed_classification = Classification(
                        **_envelope_values(
                            "classifier",
                            CLASSIFIER_VERSION,
                            AgentStatus.OK,
                            now,
                            now,
                            None,
                            1.0,
                        ),
                        doc_type=fixed_doc_type,
                        routing_tags=[],
                    )
            _write_status(runtime, case_id, CaseStatus.PROCESSING, "load_document", {})
            _record_load_event(runtime, case_id, pipeline_run, "NODE_END", {"status": "OK"})
            return {
                "document": doc_ref,
                "content": content,
                "images": rendered.images,
                "received_at": received_at,
                **({"classification": fixed_classification} if fixed_classification else {}),
            }
        except Exception as error:  # noqa: BLE001
            try:
                _record_load_event(
                    runtime,
                    case_id,
                    pipeline_run,
                    "NODE_END",
                    {"status": "ERROR", "error": type(error).__name__},
                )
            except Exception:
                logger.exception("Could not persist document-load failure audit")
            return {"infrastructure_error": f"DOCUMENT_LOAD: {type(error).__name__}"}

    def classify_call(state: GraphState) -> Classification:
        override = runtime.agent_overrides.get("classifier")
        if override is not None:
            return override(state)
        return ClassifierAgent(runtime.gateway, runtime.settings).classify(
            state["content"], state["document"].mime_type
        )

    classifier_node = instrument(
        "classifier",
        classify_call,
        _error_classification,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
        prompt_version="v2",
        wait_seconds=getattr(runtime.gateway, "wait_seconds", None),
    )

    def classify(state: GraphState) -> dict[str, Any]:
        result = classifier_node(state)
        classification = result["classifier"]
        case_id = UUID(state["case_id"])
        try:
            with Session(runtime.engine) as session, session.begin():
                case = CaseRepo(session).update_classification(case_id, classification.doc_type)
                if classification.status != AgentStatus.ERROR:
                    case.status = CaseStatus.CLASSIFIED
        except Exception as error:
            raise InfrastructureFailure("Could not persist classification") from error
        return {
            "classification": classification,
            **{k: v for k, v in result.items() if k != "classifier"},
        }

    def ocr_call(state: GraphState) -> OcrPayload:
        override = runtime.agent_overrides.get("ocr")
        if override is not None:
            return override(state)
        return OCRAgent(runtime.gateway, runtime.settings).process(
            state["content"], state["document"].mime_type, state["classification"].doc_type
        )

    ocr_node = instrument(
        "ocr",
        ocr_call,
        _error_ocr,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
        prompt_version="v3",
        wait_seconds=getattr(runtime.gateway, "wait_seconds", None),
    )

    def ocr(state: GraphState) -> dict[str, Any]:
        result = ocr_node(state)
        _write_status(runtime, UUID(state["case_id"]), CaseStatus.PROCESSING, "ocr", {})
        return {"ocr": result["ocr"], **{k: v for k, v in result.items() if k != "ocr"}}

    def kyc_call(state: GraphState) -> KycResult:
        selected = ROUTING_TABLE[state["classification"].doc_type].kyc is not None
        override = runtime.agent_overrides.get("kyc")
        if not selected:
            return _skipped_kyc()
        if override is not None:
            return override(state)
        with Session(runtime.engine) as session:
            return KycAgent(MemberRepo(session), runtime.gateway, runtime.settings).check(
                state["classification"].doc_type,
                state["ocr"],
                state["received_at"],
                state["images"],
            )

    kyc_node = instrument(
        "kyc",
        kyc_call,
        _error_kyc,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
        prompt_version="v2",
        wait_seconds=getattr(runtime.gateway, "wait_seconds", None),
    )

    def claims_call(state: GraphState) -> ClaimsResult:
        selected = ROUTING_TABLE[state["classification"].doc_type].claims
        override = runtime.agent_overrides.get("claims")
        if not selected:
            return _skipped_claims()
        if override is not None:
            return override(state)
        return ClaimsAgent(runtime.gateway, runtime.settings).extract(
            state["classification"].doc_type,
            state["ocr"],
            state["received_at"],
            state["images"],
        )

    claims_node = instrument(
        "claims",
        claims_call,
        _error_claims,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
        prompt_version="v2",
        wait_seconds=getattr(runtime.gateway, "wait_seconds", None),
    )

    def policy_call(state: GraphState) -> PolicyResult:
        selected = ROUTING_TABLE[state["classification"].doc_type].policy
        if not selected:
            return _placeholder_policy()
        override = runtime.agent_overrides.get("policy")
        if override is not None:
            return override(state)
        client = create_qdrant_client(runtime.settings)
        try:
            embedder = LocalSentenceTransformerEmbedder(runtime.settings.embedding_model)
            with Session(runtime.engine) as session:
                agent = PolicyAgent(
                    MemberRepo(session),
                    PolicyExclusionRepo(session),
                    runtime.gateway,
                    runtime.settings,
                    QdrantHybridRetriever(client, embedder),
                    (
                        DeterministicReranker()
                        if runtime.settings.llm_provider == "stub"
                        else CrossEncoderReranker()
                    ),
                )
                return agent.evaluate(
                    state["classification"].doc_type,
                    state["kyc"],
                    state["claims"],
                    state["ocr"],
                    state["received_at"],
                )
        finally:
            client.close()

    policy_node = instrument(
        "policy",
        policy_call,
        _error_policy,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
        prompt_version="v2",
        wait_seconds=getattr(runtime.gateway, "wait_seconds", None),
    )

    def fraud_call(state: GraphState) -> FraudResult:
        selected = ROUTING_TABLE[state["classification"].doc_type].fraud
        if not selected:
            return _placeholder_fraud()
        override = runtime.agent_overrides.get("fraud")
        if override is not None:
            return override(state)
        with Session(runtime.engine) as session:
            agent = FraudAgent(ClaimHistoryRepo(session), runtime.settings)
            member_id = state.get("kyc").member_ref if state.get("kyc") else None
            return agent.score(
                state["classification"].doc_type,
                member_id,
                state["claims"],
                state["kyc"],
                state["ocr"],
                state["received_at"],
                current_case_id=state["case_id"],
            )

    fraud_node = instrument(
        "fraud",
        fraud_call,
        _error_fraud,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
    )

    def orchestrator_call(state: GraphState) -> Decision:
        started_at = datetime.now(UTC)
        rule_decision, rule_trace, confidence = decide(
            state, Thresholds.from_settings(runtime.settings)
        )
        model_name: str | None = getattr(runtime.settings, "llm_text_model", None)
        try:
            prompt = PromptLoader().load("orchestrator_justify", "v2")
            model_name = prompt.resolve_model(runtime.settings)
            trace_payload = [step.model_dump(mode="json") for step in rule_trace]
            draft = prompt.invoke(
                runtime.gateway,
                runtime.settings,
                [
                    {
                        "role": "user",
                        "content": json.dumps({"rule_trace": trace_payload}, sort_keys=True),
                    }
                ],
                None,
                JustificationDraft,
            )
            justification = draft.justification
        except Exception as error:  # noqa: BLE001
            logger.warning("Orchestrator justification fallback: %s", type(error).__name__)
            justification = _template_justification(rule_trace, state)

        agent_summaries = {
            name: f"{result.status.value}; confidence={result.confidence:.2f}"
            for name in ("classification", "ocr", "kyc", "claims", "policy", "fraud")
            if (result := state.get(name)) is not None and result.status != AgentStatus.SKIPPED
        }
        result = Decision(
            **_envelope_values(
                "orchestrator",
                ORCHESTRATOR_VERSION,
                AgentStatus.OK,
                started_at,
                datetime.now(UTC),
                model_name,
                confidence,
            ),
            decision=rule_decision,
            justification=justification,
            agent_summaries=agent_summaries,
            rule_trace=rule_trace,
        )
        assert result.decision == rule_decision, "LLM justification must not alter the decision"
        return result

    orchestrator_node = instrument(
        "orchestrator",
        orchestrator_call,
        _error_orchestrator,
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
    )

    def kyc(state: GraphState) -> dict[str, Any]:
        return kyc_node(state)

    def claims(state: GraphState) -> dict[str, Any]:
        return claims_node(state)

    def policy(state: GraphState) -> dict[str, Any]:
        return policy_node(state)

    def join(state: GraphState) -> dict[str, Any]:
        _record_graph_event(runtime, state, "join", "NODE_START")
        _record_graph_event(runtime, state, "join", "NODE_END")
        return {}

    def route_specialists(state: GraphState) -> dict[str, Any]:
        _record_graph_event(runtime, state, "route_specialists", "NODE_START")
        routed_agents = sorted(route(state["classification"].doc_type))
        _record_graph_event(
            runtime,
            state,
            "route_specialists",
            "NODE_END",
            {"routed_agents": routed_agents},
        )
        return {"routed_agents": routed_agents}

    def fraud(state: GraphState) -> dict[str, Any]:
        return fraud_node(state)

    def orchestrator(state: GraphState) -> dict[str, Any]:
        result = orchestrator_node(state)
        return {
            "decision": result["orchestrator"],
            **{key: value for key, value in result.items() if key != "orchestrator"},
        }

    def mark_needs_review(state: GraphState) -> dict[str, Any]:
        case_id = UUID(state["case_id"])
        _record_graph_event(runtime, state, "mark_needs_review", "NODE_START")
        _write_status(
            runtime,
            case_id,
            CaseStatus.NEEDS_REVIEW,
            "mark_needs_review",
            {"errors": state.get("errors", []), "reason": "pipeline requires review"},
        )
        _record_graph_event(runtime, state, "mark_needs_review", "NODE_END")
        return {"terminal_status": CaseStatus.NEEDS_REVIEW.value}

    def mark_failed(state: GraphState) -> dict[str, Any]:
        case_id = UUID(state["case_id"])
        _record_graph_event(runtime, state, "mark_failed", "NODE_START")
        _write_status(
            runtime,
            case_id,
            CaseStatus.FAILED,
            "mark_failed",
            {"error": state.get("infrastructure_error", "graph failure")},
        )
        _record_graph_event(runtime, state, "mark_failed", "NODE_END")
        return {"terminal_status": CaseStatus.FAILED.value}

    def aggregate(state: GraphState) -> dict[str, Any]:
        _record_graph_event(runtime, state, "aggregate", "NODE_START")
        specialist_results = [
            state.get("kyc"),
            state.get("claims"),
            state.get("policy"),
            state.get("fraud"),
        ]
        errors = list(state.get("errors", [])) + [
            f"{item.agent}: {item.error or 'ERROR'}"
            for item in specialist_results
            if item is not None and item.status == AgentStatus.ERROR
        ]
        terminal = CaseStatus.AGGREGATED
        case_id = UUID(state["case_id"])
        try:
            with Session(runtime.engine) as session, session.begin():
                case = CaseRepo(session).update_status(case_id, terminal)
                kyc_result = state.get("kyc")
                if kyc_result is not None and kyc_result.member_ref:
                    case.member_ref = kyc_result.member_ref
                AuditRepo(session).append(
                    case_id=case_id,
                    actor_type="AGENT",
                    actor="aggregate",
                    event_type="STATUS",
                    payload={
                        "pipeline_run": state["pipeline_run"],
                        "status": terminal.value,
                        "errors": errors,
                    },
                )
        except Exception as error:
            raise InfrastructureFailure("Could not persist aggregated case state") from error
        _record_graph_event(
            runtime,
            state,
            "aggregate",
            "NODE_END",
            {"status": terminal.value},
        )
        return {"errors": errors, "terminal_status": terminal.value}

    def persist(state: GraphState) -> dict[str, Any]:
        case_id = UUID(state["case_id"])
        pipeline_run = UUID(state["pipeline_run"])
        decision = state["decision"]
        thresholds = Thresholds.from_settings(runtime.settings)
        reference_date = state["received_at"].date().isoformat()
        config_snapshot = {
            "thresholds": thresholds.model_dump(mode="json"),
            "weights": dict(DETECTOR_WEIGHTS),
            "reference_date": reference_date,
        }
        try:
            with Session(runtime.engine) as session, session.begin():
                inserted = DecisionRepo(session).add_if_absent(
                    DecisionRow(
                        case_id=case_id,
                        pipeline_run=pipeline_run,
                        decision=decision.decision,
                        confidence=Decimal(str(decision.confidence)),
                        justification=decision.justification,
                        rule_trace=[step.model_dump(mode="json") for step in decision.rule_trace],
                        config_snapshot=config_snapshot,
                    )
                )
                CaseRepo(session).update_status(case_id, CaseStatus.DECIDED)
                AuditRepo(session).append(
                    case_id=case_id,
                    actor_type="AGENT",
                    actor="orchestrator",
                    event_type="STATUS",
                    payload={"pipeline_run": str(pipeline_run), "status": CaseStatus.DECIDED.value},
                )
                if inserted:
                    AuditRepo(session).append(
                        case_id=case_id,
                        actor_type="AGENT",
                        actor="orchestrator",
                        event_type="DECISION",
                        payload={
                            "pipeline_run": str(pipeline_run),
                            "decision": decision.decision.value,
                            "confidence": decision.confidence,
                            "justification": decision.justification,
                            "rule_trace": [
                                step.model_dump(mode="json") for step in decision.rule_trace
                            ],
                            "config_snapshot": config_snapshot,
                        },
                    )
        except Exception as error:
            raise InfrastructureFailure("Could not persist decision") from error
        if inserted:
            try:
                runtime.event_publisher.publish(
                    "DECISION",
                    {
                        "case_id": str(case_id),
                        "pipeline_run": str(pipeline_run),
                        "decision": decision.decision.value,
                    },
                )
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not publish decision event: %s", type(error).__name__)
        return {"terminal_status": CaseStatus.DECIDED.value}

    return {
        "load_document": load_document,
        "classify": classify,
        "ocr": ocr,
        "route_specialists": route_specialists,
        "kyc": kyc,
        "claims": claims,
        "policy": policy,
        "join": join,
        "fraud": fraud,
        "orchestrator": orchestrator,
        "aggregate": aggregate,
        "persist": persist,
        "mark_needs_review": mark_needs_review,
        "mark_failed": mark_failed,
    }
