"""Celery tasks for case pipelines and exhausted-task handling."""

import logging
from uuid import UUID, uuid4

from celery import Task
from sqlalchemy.orm import Session

from apps.worker.celery_app import celery_app
from apps.worker.runtime import WorkerRuntime, build_runtime
from packages.core.db.repositories import AuditRepo, CaseRepo
from packages.core.enums import CaseStatus
from packages.graph.builder import build_graph, initial_state

logger = logging.getLogger(__name__)
runtime_factory = build_runtime


def _mark_failed(runtime: WorkerRuntime, case_id: UUID, pipeline_run: UUID, reason: str) -> None:
    with Session(runtime.engine) as session, session.begin():
        CaseRepo(session).update_status(case_id, CaseStatus.FAILED)
        AuditRepo(session).append(
            case_id=case_id,
            actor_type="AGENT",
            actor="celery",
            event_type="STATUS",
            payload={
                "pipeline_run": str(pipeline_run),
                "status": CaseStatus.FAILED.value,
                "reason": reason,
            },
        )


@celery_app.task(
    bind=True,
    name="apps.worker.tasks.run_pipeline",
    max_retries=2,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_pipeline(self: Task, case_id: str, pipeline_run: str | None = None) -> dict[str, str]:
    case_uuid = UUID(case_id)
    pipeline_uuid = UUID(pipeline_run) if pipeline_run else uuid4()
    runtime = runtime_factory()
    try:
        result = build_graph(runtime.graph).invoke(
            initial_state(str(case_uuid), str(pipeline_uuid))
        )
        return {
            "case_id": str(case_uuid),
            "pipeline_run": str(pipeline_uuid),
            "status": result.get("terminal_status", CaseStatus.FAILED.value),
        }
    except Exception as error:
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=error,
                args=[str(case_uuid), str(pipeline_uuid)],
                countdown=2**self.request.retries,
            )
        logger.exception("Pipeline exhausted retries for case %s", case_uuid)
        _mark_failed(runtime, case_uuid, pipeline_uuid, type(error).__name__)
        return {
            "case_id": str(case_uuid),
            "pipeline_run": str(pipeline_uuid),
            "status": CaseStatus.FAILED.value,
        }
    finally:
        runtime.close()


@celery_app.task(name="apps.worker.tasks.dead_letter_pipeline", acks_late=True)
def dead_letter_pipeline(case_id: str, pipeline_run: str, reason: str) -> None:
    runtime = runtime_factory()
    try:
        _mark_failed(runtime, UUID(case_id), UUID(pipeline_run), reason)
    finally:
        runtime.close()
