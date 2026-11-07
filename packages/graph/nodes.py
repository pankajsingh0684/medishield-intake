"""Graph node implementations and their shared runtime dependencies."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from packages.agents.claims.agent import CLAIMS_VERSION, ClaimsAgent
from packages.agents.classifier.agent import CLASSIFIER_VERSION, ClassifierAgent
from packages.agents.kyc.agent import KYC_VERSION, KycAgent
from packages.agents.ocr.agent import OCR_VERSION, OCRAgent
from packages.core.db.repositories import AuditRepo, CaseRepo, MemberRepo
from packages.core.documents import render_document
from packages.core.enums import AgentStatus, CaseStatus, DecisionKind, DocType, RiskLevel
from packages.core.llm.protocol import LLMGateway
from packages.core.models import (
    ClaimFields,
    ClaimsResult,
    Classification,
    Decision,
    DocumentRef,
    FraudResult,
    KycResult,
    OcrPayload,
    PolicyResult,
)
from packages.core.storage import S3Storage
from packages.graph.routing import ROUTING_TABLE, route
from packages.graph.state import GraphState
from packages.graph.wrapper import InfrastructureFailure, instrument

logger = logging.getLogger(__name__)


@dataclass
class GraphRuntime:
    engine: Engine
    storage: S3Storage
    settings: Any
    gateway: LLMGateway
    redis_client: Redis | None = None
    agent_overrides: dict[str, Callable[[GraphState], Any]] = field(default_factory=dict)
    retry_backoff_seconds: float = 1.0


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
        **_envelope_values("policy", "0.1.0", AgentStatus.SKIPPED, now, now, None, 1.0),
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


def _placeholder_orchestrator() -> Decision:
    now = datetime.now(UTC)
    return Decision(
        **_envelope_values("orchestrator", "0.1.0", AgentStatus.SKIPPED, now, now, None, 1.0),
        decision=DecisionKind.ESCALATE,
        justification="Decision logic is not implemented in this pipeline step.",
        agent_summaries={},
        rule_trace=[],
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
            with Session(runtime.engine) as session:
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
            _write_status(runtime, case_id, CaseStatus.PROCESSING, "load_document", {})
            _record_load_event(runtime, case_id, pipeline_run, "NODE_END", {"status": "OK"})
            return {
                "document": doc_ref,
                "content": content,
                "images": rendered.images,
                "received_at": received_at,
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
        prompt_version="v1",
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
        prompt_version="v1",
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
        prompt_version="v1",
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
        prompt_version="v1",
    )

    policy_node = instrument(
        "policy",
        lambda state: _placeholder_policy(),
        lambda start, finish, error: _placeholder_policy(),
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
    )
    fraud_node = instrument(
        "fraud",
        lambda state: _placeholder_fraud(),
        lambda start, finish, error: _placeholder_fraud(),
        engine=runtime.engine,
        redis_client=runtime.redis_client,
        timeout_seconds=timeout,
        backoff_seconds=runtime.retry_backoff_seconds,
    )
    orchestrator_node = instrument(
        "orchestrator",
        lambda state: _placeholder_orchestrator(),
        lambda start, finish, error: _placeholder_orchestrator(),
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
        selection = ROUTING_TABLE[state["classification"].doc_type]
        if not selection.policy:
            return policy_node(state)
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
        if not ROUTING_TABLE[state["classification"].doc_type].fraud:
            return fraud_node(state)
        return fraud_node(state)

    def orchestrator(state: GraphState) -> dict[str, Any]:
        return orchestrator_node(state)

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
        terminal = CaseStatus.NEEDS_REVIEW if errors else CaseStatus.AGGREGATED
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
        "mark_needs_review": mark_needs_review,
        "mark_failed": mark_failed,
    }
