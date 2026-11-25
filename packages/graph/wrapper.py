"""Audit, retry, timeout, and persistence wrapper for graph agents."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from packages.core.db.models import AgentRun
from packages.core.db.repositories import AgentRunRepo, AuditRepo
from packages.core.models import Envelope
from packages.graph.state import GraphState

logger = logging.getLogger(__name__)


class InfrastructureFailure(RuntimeError):
    """Persistence failure that must escape the agent boundary and fail the graph."""


def _event(
    engine: Engine,
    case_id: UUID,
    pipeline_run: UUID,
    agent: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    try:
        with Session(engine) as session, session.begin():
            AuditRepo(session).append(
                case_id=case_id,
                actor_type="AGENT",
                actor=agent,
                event_type=event_type,
                payload={"pipeline_run": str(pipeline_run), **payload},
            )
    except Exception as error:
        raise InfrastructureFailure("Could not persist graph audit event") from error


def _save_run(
    engine: Engine,
    case_id: UUID,
    pipeline_run: UUID,
    envelope: Envelope,
    prompt_version: str | None,
) -> None:
    try:
        with Session(engine) as session, session.begin():
            AgentRunRepo(session).save(
                AgentRun(
                    case_id=case_id,
                    pipeline_run=pipeline_run,
                    agent=envelope.agent,
                    agent_version=envelope.agent_version,
                    status=envelope.status.value,
                    model=envelope.model,
                    prompt_version=prompt_version,
                    confidence=Decimal(str(envelope.confidence)),
                    output=envelope.model_dump(mode="json"),
                    error=envelope.error,
                    started_at=envelope.started_at,
                    finished_at=envelope.finished_at,
                )
            )
    except Exception as error:
        raise InfrastructureFailure("Could not persist graph agent result") from error


def _publish(redis_client: Redis | None, case_id: UUID, envelope: Envelope) -> None:
    if redis_client is None:
        return
    try:
        redis_client.publish(
            f"case:{case_id}",
            envelope.model_dump_json(),
        )
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "Could not publish agent event for case %s: %s", case_id, type(error).__name__
        )


def instrument[EnvelopeT: Envelope](
    agent_name: str,
    call: Callable[[GraphState], EnvelopeT],
    error_factory: Callable[[datetime, datetime, Exception], EnvelopeT],
    *,
    engine: Engine,
    redis_client: Redis | None,
    timeout_seconds: int,
    retries: int = 2,
    backoff_seconds: float = 1.0,
    prompt_version: str | None = None,
    wait_seconds: Callable[[], float] | None = None,
) -> Callable[[GraphState], dict[str, object]]:
    """Wrap an agent call; exhausted agent exceptions become typed ERROR envelopes."""

    def wrapped(state: GraphState) -> dict[str, object]:
        case_id = UUID(state["case_id"])
        pipeline_run = UUID(state["pipeline_run"])
        started_at = datetime.now(UTC)
        _event(engine, case_id, pipeline_run, agent_name, "NODE_START", {})
        result: Envelope
        final_error: Exception | None = None
        for attempt in range(retries + 1):
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(call, state)
            try:
                import time

                started_wait = wait_seconds() if wait_seconds is not None else 0.0
                started_perf = time.monotonic()
                while True:
                    limiter_waited = (
                        wait_seconds() if wait_seconds is not None else 0.0
                    ) - started_wait
                    elapsed_in_flight = time.monotonic() - started_perf - limiter_waited
                    remaining = timeout_seconds - elapsed_in_flight
                    if remaining <= 0:
                        raise FutureTimeout()
                    try:
                        result = future.result(timeout=min(1.0, remaining))
                        break
                    except FutureTimeout:
                        continue
                final_error = None
                executor.shutdown(wait=True)
                break
            except FutureTimeout:
                final_error = TimeoutError(f"{agent_name} exceeded {timeout_seconds}s")
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                if attempt < retries:
                    import time

                    time.sleep(backoff_seconds * (2**attempt))
            except Exception as error:  # noqa: BLE001
                final_error = error
                executor.shutdown(wait=True)
                if attempt < retries:
                    import time

                    time.sleep(backoff_seconds * (2**attempt))
        if final_error is not None:
            result = error_factory(started_at, datetime.now(UTC), final_error)
        _save_run(engine, case_id, pipeline_run, result, prompt_version)
        _event(
            engine,
            case_id,
            pipeline_run,
            agent_name,
            "NODE_END",
            {"status": result.status.value, "confidence": result.confidence},
        )
        _publish(redis_client, case_id, result)
        update: dict[str, object] = {agent_name: result}
        if result.status.value == "ERROR":
            update["errors"] = [f"{agent_name}: {result.error or 'ERROR'}"]
        return update

    return wrapped
